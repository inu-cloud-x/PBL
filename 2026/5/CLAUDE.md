# DAPP-WEB — Trustless dApp PoC

Ethereum Sepolia에서 동작하는 Passkey(WebAuthn) 기반 trustless dApp PoC.
개인키 없이 Passkey만으로 로그인 → AA 지갑(ERC-4337) 생성 → 온체인 데이터 저장.
RPC 응답은 Helios 라이트 클라이언트로 검증한다.

---

## 배포된 컨트랙트 (Sepolia, chainId 11155111)

| 컨트랙트 | 주소 |
|---|---|
| PasskeyRegistry | `0x9140b5f38e69d8b0a21b8232a1ddd600ce18e496` |
| CoinbaseSmartWallet (impl) | `0xe424830754c1c7e2f6115af5dfda406b62f93069` |
| CoinbaseSmartWalletFactory | `0xe47c9418c7193dcc17ae564103cb0c3f28bf2b60` |
| DataStore | `0x505c35913d6475a2ea7a92c0275be7a780c8b7f3` |
| MiniENS | `0xD945d0eFc0d9DdBc758dF9E67CE03eA431e670bd` |
| VotingRegistry | `0xC80E447D45a06d121B118D3ff252Be6EdC9d7176` |
| VCRegistry | `0xB499a934056F605155186C716bD8F10AFefA614F` |

브로드캐스트 아티팩트: `broadcast/Deploy.s.sol/11155111/run-latest.json`, `broadcast/DeployENS.s.sol/11155111/run-latest.json`, `broadcast/DeployVoting.s.sol/11155111/run-latest.json`, `broadcast/DeployVC.s.sol/11155111/run-latest.json`

---

## 외부 서비스

| 서비스 | 용도 | 환경변수 |
|---|---|---|
| ZeroDev bundler | ERC-4337 UserOperation 번들링 | `VITE_BUNDLER_URL` |
| ZeroDev paymaster (선택) | 가스비 후원 | `VITE_PAYMASTER_URL` |
| Alchemy / Infura / QuickNode | Execution RPC (Helios 동기화 + 상태 조회) | `VITE_EXECUTION_RPC_URL` |
| publicnode Beacon API | Helios consensus 동기화 (CORS 필요 → beacon-proxy 경유) | `VITE_CONSENSUS_RPC_URL` |
| Vercel Edge Function | `/api/beacon-proxy` CORS 우회용 프록시 | — |

로컬 개발 시 beacon proxy는 `vite.config.ts`의 `server.proxy`가 처리한다 (기본값: `lodestar-sepolia.chainsafe.io`). 프로덕션에서는 `api/beacon-proxy.ts` Vercel Edge Function이 담당한다.

---

## 핵심 파일 위치

### TypeScript / React
| 파일 | 역할 |
|---|---|
| `src/config.ts` | 환경변수 로드. `getMissingEnvKeys()` (필수), `getMissingOptionalEnvKeys()` (v2 선택) |
| `src/lib/passkey.ts` | WebAuthn 등록/로드. P-256 좌표 추출 후 localStorage에 직렬화 |
| `src/lib/wallet.ts` | ZeroDev Kernel(v0.3.3) + PasskeyValidator(V0_0_3_PATCHED)로 AA 클라이언트 생성. PasskeyRegistry.link() 호출 포함 |
| `src/lib/helios.ts` | Helios Web Worker 수명 관리. comlink로 메인 스레드와 통신 |
| `src/lib/datastore.ts` | DataStore 컨트랙트 읽기/쓰기. 읽기는 반드시 Helios 클라이언트 경유 |
| `src/lib/ens.ts` | MiniENS 컨트랙트 읽기/쓰기. register/release (AA), resolve/reverseLookup (Helios) |
| `src/lib/voting.ts` | VotingRegistry 컨트랙트. createProposal/vote (AA), getRecent/hasVoted (Helios) |
| `src/lib/did.ts` | P-256 공개키 → `did:key` 파생. `derivePasskeyDid`, `publicKeyBytesFromDid`, `storedKeyToPub` |
| `src/lib/vc.ts` | VC 빌드/서명/검증, localStorage 보관, VCRegistry 컨트랙트 연동 (AA + Helios) |
| `src/hooks/useENSName.ts` | 주소 → ENS 이름 변환 훅. 모듈 레벨 캐시. `invalidateENSCache()` 포함 |
| `src/workers/helios.worker.ts` | @a16z/helios WASM을 Worker 스레드에서 실행. 12초 keepalive 타이머 포함 |
| `src/components/Login.tsx` | Passkey 등록/로그인 UI |
| `src/components/Nav.tsx` | 탭 내비게이션 (데이터 / ENS 이름 / 투표) |
| `src/components/DataEditor.tsx` | 텍스트 입력 → DataStore.store() 호출 (300 bytes 제한) |
| `src/components/DataViewer.tsx` | Helios로 DataStore.getAll() 읽기. useENSName으로 내 이름 표시 |
| `src/components/ENSRegistrar.tsx` | ENS 이름 등록·해제·조회 UI |
| `src/components/CreateProposal.tsx` | 제안 생성 폼 (제목 100b / 설명 500b / 기간) |
| `src/components/ProposalList.tsx` | Helios로 최신 20개 제안 조회. Helios 상태 관리 |
| `src/components/ProposalCard.tsx` | 제안 카드 — 상태 배지, ENS 이름, 투표 바 차트 (CSS) |
| `src/components/VotePanel.tsx` | Yes/No/기권 투표 버튼. hasVoted 확인 후 결과 표시 |
| `src/components/vc/VCTab.tsx` | VC 탭 컨테이너. Helios 상태 관리 + sub-nav (형식/받은요청/내요청/보관함) |
| `src/components/vc/FormatBoard.tsx` | VC 형식 게시판. 등록(ENS 필요), active 목록, 요청 모달 |
| `src/components/vc/IssuerInbox.tsx` | Issuer 받은 요청함. 승인 (Passkey 서명 + 온체인 + JSON 다운로드), 거절 |
| `src/components/vc/MyRequests.tsx` | 내 요청 현황. 형식별 상태 배지 (대기/승인/거절) |
| `src/components/vc/MyCredentials.tsx` | 내 VC 보관함. 가져오기(서명+온체인 검증), 온체인 확인, JSON 다운로드, 삭제 |
| `api/beacon-proxy.ts` | Vercel Edge Function. Beacon API CORS 우회 프록시 |

### Solidity
| 파일 | 역할 |
|---|---|
| `contracts/PasskeyRegistry.sol` | credentialIdHash → AA 주소 매핑. 덮어쓰기 불가 |
| `contracts/DataStore.sol` | 주소별 `bytes[]` + timestamp 저장. swap-and-pop 삭제 |
| `contracts/MiniENS.sol` | 이름 ↔ 주소 양방향 매핑. register/release/resolve/reverseLookup |
| `contracts/VotingRegistry.sol` | 제안 생성/투표. Choice enum (Yes/No/Abstain), hasVoted 매핑 |
| `contracts/VCRegistry.sol` | VC 형식 등록(ENS 필요), 요청/승인/거절, 발급 hash 온체인 기록 |
| `contracts/coinbase/CoinbaseSmartWallet.sol` | ERC-4337 EP v0.6 스마트 계정. UUPS 제거, WebAuthn 서명 지원 |
| `contracts/coinbase/CoinbaseSmartWalletFactory.sol` | ERC-1167 최소 프록시로 지갑 배포 |
| `script/Deploy.s.sol` | 4개 컨트랙트 순서대로 배포, .env 변수 콘솔 출력 |
| `script/DeployENS.s.sol` | MiniENS 배포 |
| `script/DeployVoting.s.sol` | VotingRegistry 배포 |
| `script/DeployVC.s.sol` | VCRegistry 배포. `VITE_ENS_ADDRESS` 환경변수로 MiniENS 주소 주입 |

### Foundry 의존성 (git submodule)
- `lib/forge-std` — 테스트/스크립트 유틸
- `lib/solady` — LibClone(ERC-1167), SignatureCheckerLib, Receiver
- `lib/webauthn-sol` — WebAuthn.verify() on-chain 구현 (FCL secp256r1)
- `lib/account-abstraction` — ERC-4337 인터페이스 (IAccount, UserOperation)

---

## 환경변수 (.env)

`.env.example` 참고. 필수 키:

```
VITE_TARGET_CHAIN_ID=11155111
VITE_EXECUTION_RPC_URL=
VITE_CONSENSUS_RPC_URL=
VITE_BUNDLER_URL=
VITE_DATA_STORE_ADDRESS=
VITE_ZERODEV_PROJECT_ID=
```

선택 키: `VITE_PAYMASTER_URL`, `VITE_PASSKEY_REGISTRY_ADDRESS`, `VITE_SMART_WALLET_IMPL`, `VITE_SMART_WALLET_FACTORY`, `VITE_MINI_ENS_ADDRESS`, `VITE_VOTING_REGISTRY_ADDRESS`, `VITE_VC_REGISTRY_ADDRESS`

---

## 알려진 제약사항 / 함정

1. **Helios 동기화 지연**: `initHelios()`는 첫 호출 시 ~10–30초 걸린다. `_initPromise` 싱글턴으로 중복 초기화를 막는다.

2. **Helios "out of sync" 오류**: 탭을 오래 방치하면 WASM sync loop가 멈춘다. `isOutOfSync(e)` 체크 후 `resetHelios()` → `initHelios()` 재시도 필요.

3. **Beacon API CORS**: 브라우저에서 Beacon REST API를 직접 호출하면 CORS 차단된다. 반드시 `/api/beacon-proxy` 경유. 로컬은 vite proxy, 프로덕션은 Vercel Edge Function.

4. **Helios finalized checkpoint**: `waitSynced()` 전에 `/eth/v1/beacon/blocks/finalized/root`로 체크포인트를 직접 주입한다. 비finalized 블록을 사용하면 beacon node에서 404가 난다.

5. **DataStore swap-and-pop**: `remove(index)` 호출 시 배열 순서가 바뀐다. 클라이언트에서 timestamp 기준으로 재정렬해야 하고, 삭제 시 index를 바로 무효화해야 한다.

6. **CoinbaseSmartWallet EP 버전**: 컨트랙트는 EP v0.6 (`0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789`) 하드코딩. ZeroDev SDK에서 `entryPoint07Address`(v0.7)를 쓰는 것과 혼용되지 않도록 주의 (현재 wallet.ts는 v0.7 SDK 사용 — DECISIONS.md 참조).

7. **WebAuthn rpID**: `window.location.hostname` 기반. localhost에서 등록한 Passkey는 배포된 도메인에서 사용 불가.

8. **PasskeyValidator 버전**: `PasskeyValidatorContractVersion.V0_0_3_PATCHED` 고정. ZeroDev SDK 업그레이드 시 확인 필요.

9. **VC import 시 본인 발급 기록과 hash 매칭 필요**: `MyCredentials.tsx`의 import 흐름은 `vcListIssuedToMe(myAddress)`에서 `jsonHash`와 비교한다. 다른 주소로 발급된 VC는 import 거부된다.

10. **Issuer 승인 시 Passkey assertion이 한 번 더 필요**: `signVc()`는 `navigator.credentials.get()`을 호출해 지문 인증을 다시 요구한다. UI에서 사용자에게 사전 안내 필요.

---

## 개발 / 배포 명령

```bash
# 로컬 개발
npm run dev

# 컨트랙트 빌드
forge build

# Sepolia 배포 (PRIVATE_KEY, RPC_URL 필요)
forge script script/Deploy.s.sol --rpc-url $RPC_URL --broadcast --private-key $PRIVATE_KEY

# v3 VCRegistry 배포 (VITE_MINI_ENS_ADDRESS가 .env에 있어야 함)
forge script script/DeployVC.s.sol --rpc-url $VITE_EXECUTION_RPC_URL --broadcast --private-key $PRIVATE_KEY

# 프론트엔드 빌드
npm run build
```

배포 플랫폼: **Vercel** (vercel.json, `.vercel/repo.json` 참조)
