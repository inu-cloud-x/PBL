# 탈중앙화 dApp PoC 구현 작업 지시

> Claude Code 작업 지시 문서. 진행 전 본 문서를 처음부터 끝까지 읽고, 모호한 점이 있으면 코드를 작성하기 전에 먼저 질문할 것.

---

## 1. 프로젝트 개요

Trustless · Gasless 웹 프론트엔드 인프라를 PoC 수준으로 구현한다. 사용자는 시드 구문 없이 Passkey로 로그인하고, dApp이 RPC 응답을 직접 검증한다.

핵심 설계:

- **인증:** Passkey (WebAuthn / secp256r1)
- **지갑:** ERC-4337 Account Abstraction 스마트 컨트랙트 지갑
- **읽기 검증:** Helios light client + Public RPC (브라우저 내장 WASM)
- **쓰기 경로:** AA 지갑 → 외부 Bundler → L2 블록체인
- **배포:** Vercel 정적 호스팅, Zero backend (Edge Function은 CORS 프록시만)

## 2. 기능 요구사항

사용자가 할 수 있는 일은 다음 3가지뿐이다:

1. **Write** — 300 bytes 이하 임의 데이터를 온체인에 기록
2. **Read** — 자신이 기록한 데이터를 조회 (Helios 검증을 통과한 데이터만 신뢰)
3. **Delete** — 자신이 기록한 데이터를 삭제

별도의 회원가입/로그인 폼은 없다. Passkey 생성·인증이 그 역할을 한다.

## 3. 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| 빌드 | Vite + React 18 + TypeScript | CSR |
| 체인 인터랙션 | `viem` | ethers 금지 |
| ERC-4337 클라이언트 | `permissionless` | UserOperation 생성·제출 |
| WebAuthn | `@simplewebauthn/browser` | |
| AA 스마트 지갑 | Coinbase Smart Wallet (Passkey owner) 권장 | 또는 동급의 P256 검증 지원 AA 지갑. 다른 선택을 한다면 사유를 보고할 것 |
| Light Client | `helios` (WASM 빌드) | 브라우저 내 RPC 응답 검증 |
| 컨트랙트 도구 | Foundry | |
| 대상 체인 | Base 또는 Arbitrum (RIP-7212 precompile 보유 L2) | **둘 중 어느 쪽을 쓸지 작업 시작 전에 확인할 것** |
| 배포 | Vercel | |

## 4. 외부 의존성 (추후 주입)

다음 값들은 환경 변수로만 다루고, 코드에 하드코딩하지 않는다. 현재는 비워 둔 상태로 진행한다:

```env
VITE_TARGET_CHAIN_ID=
VITE_EXECUTION_RPC_URL=        # L2 Public RPC (TBD)
VITE_CONSENSUS_RPC_URL=        # L1 Beacon endpoint (Helios consensus)
VITE_BUNDLER_URL=              # 외부 ERC-4337 Bundler (TBD)
VITE_PAYMASTER_URL=            # 외부 Paymaster (선택)
VITE_DATA_STORE_ADDRESS=       # DataStore 컨트랙트 주소
VITE_SMART_WALLET_FACTORY=     # AA 지갑 팩토리 주소
```

`.env.example`을 함께 만들어 둘 것. 값이 비었을 때 앱은 mock으로 우회하지 말고 환경변수 미설정 상태를 UI에 그대로 노출한다.

## 5. 스마트 컨트랙트

`contracts/DataStore.sol` 한 개만 작성한다.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract DataStore {
    mapping(address => bytes) private data;
    event Updated(address indexed user, uint256 length);
    event Deleted(address indexed user);

    function set(bytes calldata value) external {
        require(value.length <= 300, "max 300 bytes");
        data[msg.sender] = value;
        emit Updated(msg.sender, value.length);
    }

    function clear() external {
        delete data[msg.sender];
        emit Deleted(msg.sender);
    }

    function get(address user) external view returns (bytes memory) {
        return data[user];
    }
}
```

**주의:** `msg.sender`는 사용자의 AA 스마트 지갑 주소다(EOA가 아님). UI에 표시하는 "내 주소"도 이 AA 주소여야 한다.

## 6. 알려진 함정과 처리 방침

원본 아키텍처 문서에서 사전에 식별된 함정. 빠짐없이 대응할 것:

- **Vite + WASM:** Helios는 Rust/WASM 모듈. `vite-plugin-wasm`, `vite-plugin-top-level-await`를 `vite.config.ts`에 반드시 적용.
- **Helios L1/L2 분리:** `consensusRPC`는 L1 Beacon, `executionRPC`는 타겟 L2(Base/Arbitrum)로 분리 설정한다. 같은 체인으로 묶지 말 것.
- **Beacon API CORS:** Public Beacon 노드는 브라우저 CORS를 차단할 수 있다. `api/beacon-proxy.ts` Vercel Edge Function으로 얇은 패스스루 프록시를 둔다. 로직 추가 금지.
- **RPC Sticky Session:** Public RPC가 라운드 로빈이면 블록 동기화가 엇갈린다. 가능하면 sticky session 옵션을 켜고, 안 되면 단일 엔드포인트로 고정.
- **Bundler URL 노출:** `VITE_*`는 빌드 산출물에 박힌다. Bundler 제공자 측에서 Vercel 도메인 Origin allowlist를 설정해야 한다는 점을 README에 명시.
- **개인키 절대 금지:** 어떤 경우에도 EOA 개인키를 `localStorage`·메모리·IndexedDB에 저장하지 않는다. 모든 서명은 Passkey(WebAuthn)로만 이루어진다.
- **검증 우회 금지:** Helios 검증이 실패하면 fallback으로 raw RPC 응답을 신뢰하지 않는다. 실패는 실패로 UI에 표시한다.

## 7. 디렉터리 구조 (제안)

```
.
├─ contracts/
│  └─ DataStore.sol
├─ api/
│  └─ beacon-proxy.ts          # Vercel Edge Function (CORS 패스스루)
├─ src/
│  ├─ main.tsx
│  ├─ App.tsx
│  ├─ config.ts                # env 로딩, 체인/주소 설정
│  ├─ lib/
│  │  ├─ passkey.ts            # WebAuthn 등록/서명
│  │  ├─ wallet.ts             # AA Smart Wallet 클라이언트 (permissionless)
│  │  ├─ helios.ts             # Helios WASM 초기화 + 검증 RPC 래퍼
│  │  └─ datastore.ts          # set/clear/get 호출 (get은 helios 경유)
│  └─ components/
│     ├─ Login.tsx
│     ├─ DataEditor.tsx        # 바이트 카운터 포함, 300 초과 시 제출 비활성
│     └─ DataViewer.tsx
├─ .env.example
├─ vite.config.ts
└─ README.md
```

## 8. 구현 단계

각 Phase는 별도 커밋으로 분리하고, 끝날 때마다 동작을 확인한 뒤 다음으로 넘어간다. Phase 단위로 보고할 것.

### Phase 1 — 프로젝트 부트스트랩
- Vite + React + TS 초기화
- `vite-plugin-wasm`, `vite-plugin-top-level-await` 설정
- 의존성 설치: `viem`, `permissionless`, `@simplewebauthn/browser`
- `.env.example`과 `src/config.ts` 작성
- `npm run dev`가 깨끗하게 뜨는지 확인

### Phase 2 — Passkey + AA 지갑
- `lib/passkey.ts`: WebAuthn 등록(`navigator.credentials.create`) / 인증(`navigator.credentials.get`)
- `lib/wallet.ts`: Passkey 공개키를 owner로 하는 AA 스마트 지갑 계정 생성
- permissionless의 smart account client로 빈 UserOperation 빌드 테스트
- 로그인 화면: 신규 사용자는 Passkey 생성, 기존 사용자는 인증 후 동일한 AA 주소로 복원
- **검증:** 같은 Passkey로 재진입 시 동일한 AA 주소가 나와야 한다

### Phase 3 — DataStore 연동
- `contracts/DataStore.sol` Foundry로 컴파일·배포 스크립트 작성
- `lib/datastore.ts`: `set` / `clear`는 AA 경유 UserOperation, `get`은 RPC 조회
- UI:
  - `DataEditor`: textarea + 실시간 바이트 카운터, 300 초과 시 제출 버튼 비활성
  - `DataViewer`: 현재 저장값 표시 + 삭제 버튼
- **검증:** Write → Read → Delete가 한 번의 사이클로 동작

### Phase 4 — Helios 통합 (Trustless read)
- `lib/helios.ts`: WASM 초기화, consensus/execution RPC 주입
- Read 경로(`datastore.get`)를 Helios 검증 RPC로 교체
- `api/beacon-proxy.ts` Edge Function 작성, `VITE_CONSENSUS_RPC_URL`을 프록시로 향하게
- 검증 실패 시 UI에 명시적으로 "데이터 검증 실패" 표시 (raw 데이터로 fallback 금지)
- **검증:** Helios가 정상 동기화된 후에만 Read가 데이터를 노출

### Phase 5 — 배포
- Vercel 프로젝트 연결, 환경변수 등록
- Bundler 대시보드에서 Vercel 도메인 allowlist 추가
- 프로덕션 빌드에서 WASM과 top-level await가 정상 동작하는지 확인
- README에 환경변수, Bundler allowlist, 컨트랙트 주소 기록

## 9. 작업 규칙

- 각 Phase 끝에 동작 결과(스크린샷 또는 명령 출력)와 함께 보고 후 다음으로 진행.
- 환경변수가 비어 있다고 mock으로 우회하지 않는다.
- Passkey를 우회하는 백도어 인증(이메일/비밀번호 등)을 만들지 않는다.
- Helios 검증을 우회하는 fallback을 만들지 않는다.
- 작업 시작 전 다음 사항을 확정한다:
  1. 대상 체인 (Base / Arbitrum)
  2. AA 지갑 컨트랙트 (Coinbase Smart Wallet 권장, 다르게 가려면 사유)
  3. Paymaster 사용 여부 (없으면 PoC 단계에서 AA 지갑이 자체 ETH로 가스 부담)

위 3가지가 결정되지 않았다면 코드 작성 전에 먼저 묻는다.

Phase 1부터 시작.