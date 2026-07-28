# Architecture Decisions

PoC 진행 중 내린 주요 결정과 이유를 기록한다.
같은 결정을 다음 세션에서 다시 논의하지 않기 위함.

---

## 1. CoinbaseSmartWallet을 포크해서 직접 배포한 이유

**결정**: Coinbase의 오픈소스 스마트 지갑 컨트랙트를 `contracts/coinbase/`에 복사해 직접 배포.

**이유**:
- Coinbase의 프로덕션 배포 컨트랙트는 UUPS 업그레이드 가능하도록 설계됨. PoC에서는 "불변 컨트랙트"가 신뢰 모델의 핵심이므로 UUPS 로직을 제거했다.
- 외부 배포 주소를 그대로 사용하면 Coinbase가 impl을 교체할 수 있다 → 우리가 통제하지 못하는 신뢰 가정이 생긴다.
- 직접 배포하면 컨트랙트 코드가 broadcast 아티팩트로 온체인 검증 가능하다.

**변경 내용**: `CoinbaseSmartWallet.sol`에서 UUPS(`UUPSUpgradeable`, `_authorizeUpgrade`) 관련 코드 제거. 나머지 로직(WebAuthn 서명 검증, MultiOwnable, ERC-1167 factory 패턴)은 원본 유지.

---

## 2. ZeroDev를 번들러로 쓰되 PasskeyValidator는 ZeroDev SDK 것을 사용한 이유

**결정**: 번들러는 ZeroDev infra를 사용하되 (`VITE_BUNDLER_URL`), Paymaster는 선택 사항으로 두고 PasskeyValidator는 ZeroDev SDK(`@zerodev/passkey-validator`)의 것을 그대로 사용.

**이유 — 번들러로 ZeroDev 사용**:
- ERC-4337 번들러를 직접 운영하는 것은 PoC 범위를 초과한다 (번들러 노드, MEV 보호, mempool 관리 등).
- ZeroDev는 Sepolia에서 안정적인 번들러를 제공하며, `@zerodev/sdk`와 통합이 잘 돼 있다.
- 번들러는 UserOperation을 릴레이할 뿐, 트랜잭션 내용을 검열하거나 수정할 권한이 없다. 번들러를 신뢰해야 하는 것은 "트랜잭션이 채굴될 것"이지 "데이터의 무결성"이 아니다.

**이유 — Paymaster를 선택 사항으로 유지**:
- Paymaster는 가스비를 후원하는 역할이며, Paymaster가 없어도 지갑에 ETH가 있으면 동작한다.
- 신뢰 모델상 Paymaster는 가스비 지불 순서를 거부할 수 있지만 트랜잭션 내용을 변조하지는 못한다.
- `VITE_PAYMASTER_URL`이 없으면 wallet.ts에서 paymaster를 붙이지 않는다.

**이유 — ZeroDev PasskeyValidator 사용**:
- on-chain WebAuthn 서명 검증(webauthn-sol)을 직접 연결하는 커스텀 validator를 만들 수 있지만, ZeroDev의 `V0_0_3_PATCHED`는 이미 이를 구현하고 있고 Kernel v0.3.3과 통합 테스트돼 있다.
- PoC 목적으로는 재구현보다 검증된 라이브러리 사용이 적절하다.

**주의**: wallet.ts에서 `entryPoint07Address`(EP v0.7)를 쓰는데 배포된 CoinbaseSmartWallet은 EP v0.6을 하드코딩하고 있다. 현재 구조에서 ZeroDev Kernel이 실제 AA 실행을 담당하므로 두 컨트랙트가 충돌하지 않는다 — Kernel이 EP v0.7로 동작하고, CoinbaseSmartWallet은 현재 직접 호출되지 않고 있다. 향후 CoinbaseSmartWallet을 직접 사용하려면 EP 버전을 맞춰야 한다.

---

## 3. Helios로 RPC 응답을 검증하는 방식

**결정**: 데이터 읽기(`datastoreGetAll`)는 반드시 Helios 라이트 클라이언트를 경유한다. 직접 RPC fallback 없음.

**이유**:
- "Trustless" dApp의 핵심 가정은 RPC 노드를 신뢰하지 않는 것이다. 일반 JSON-RPC 응답은 노드가 임의로 조작할 수 있다.
- Helios(`@a16z/helios`)는 Ethereum 컨센서스 레이어와 동기화해 BLS 서명 + Merkle proof로 응답을 검증한다.
- WASM 무거운 작업을 Web Worker에서 실행해 메인 스레드 블로킹을 방지한다 (`helios.worker.ts`).
- 쓰기 트랜잭션(UserOperation)은 번들러 경유이므로 Helios가 아닌 번들러가 처리한다. 쓰기 결과 확인은 다음 읽기(Helios)에서 이루어진다.

**구현 디테일**:
- Helios Worker는 싱글턴(`_initPromise` 패턴)으로 관리 — 컴포넌트마다 독립 init하면 동기화가 N번 발생한다.
- `isOutOfSync()`: Helios가 beacon chain과 멀어지면(탭 방치 등) "out of sync" / "maximum proof window" 에러가 난다. 이 경우 `resetHelios()` → `initHelios()` 재시도.
- consensus RPC는 CORS 때문에 브라우저에서 직접 호출 불가 → `/api/beacon-proxy` 경유 필수.
- `fetchFinalizedCheckpoint()`: `waitSynced()` 전에 finalized 블록 루트를 명시적으로 주입. 없으면 Helios가 비finalized 블록을 기준으로 잡아 beacon node 404가 발생한다.

---

## 4. PasskeyRegistry를 별도 컨트랙트로 분리한 이유

**결정**: credentialIdHash → AA 주소 매핑을 DataStore나 wallet 컨트랙트 내부에 두지 않고 독립 컨트랙트로 분리.

**이유**:
- 크로스 서비스 디스커버리: 다른 dApp이 동일한 PasskeyRegistry를 조회해 같은 Passkey로 연결된 AA 지갑 주소를 찾을 수 있다.
- DataStore와 라이프사이클이 다르다 — DataStore는 교체될 수 있지만 PasskeyRegistry는 영구적이어야 한다.
- 등록은 AA 계정 자신이 호출(`msg.sender = AA 주소`)하므로 별도 권한 관리가 필요 없다.
- 덮어쓰기 금지(`require(accountOf[...] == address(0))`)로 탈취 시나리오를 차단한다.

---

## 5. DataStore에서 swap-and-pop 삭제를 선택한 이유

**결정**: `remove(index)`가 swap-and-pop으로 구현됨 — 마지막 원소를 삭제 위치로 이동하고 pop.

**이유**:
- 순서를 유지하는 삭제(`shift`)는 O(n) 스토리지 write가 발생해 가스비가 비싸다.
- swap-and-pop은 O(1). 순서 보장이 필요 없으므로(timestamp로 클라이언트 정렬) 이 방식이 적합.
- 클라이언트(`datastoreGetAll`)에서 timestamp DESC 정렬하므로 온체인 순서는 무의미하다.
- **주의**: 삭제 후 storage index가 바뀐다. UI에서 여러 항목을 연속 삭제할 때 목록을 새로고침해야 한다.

---

## 7. 익명 투표의 범위 — ZK 제외, 가명 방식 선택

**결정**: 온체인 완전 익명(ZK proof) 투표를 구현하지 않는다. AA 지갑 주소 기반의 가명(pseudonymous) 투표로 처리하고, UI에서 MiniENS 이름으로 원시 주소를 감춘다.

**이유**:
- ZK 기반 익명 투표(Semaphore, MACI 등)는 별도의 ZK 회로 설계, 증명 생성 클라이언트, 검증자 컨트랙트가 필요하다. 이 PoC의 범위를 크게 초과한다.
- AA 지갑 주소는 EOA와 달리 Passkey 자격증명에 묶여 있고 PasskeyRegistry를 통해 식별 가능하다. 완전한 익명성은 아니지만, EOA 직접 노출보다 강한 프라이버시 격리를 제공한다.
- MiniENS 이름 레이어를 통해 사용자가 선택한 가명으로 투표 결과를 표시한다. 실명 없이 참여 가능하다.
- 컨트랙트의 `hasVoted(proposalId, address)` 구조는 향후 ZK 익명 투표(Semaphore group membership proof)로 교체할 수 있도록 설계됐다.

---

## 6. Vite + React 선택, Next.js 미사용

**결정**: 프론트엔드는 Vite + React SPA. SSR 없음.

**이유**:
- Helios WASM은 브라우저 전용이다 — Node.js 환경에서 실행되는 SSR과 호환되지 않는다.
- Vercel Edge Function(`api/beacon-proxy.ts`)으로 서버 기능이 필요한 부분만 분리했다.
- `vite-plugin-wasm`으로 WASM 번들링이 간단하게 해결된다.

---

## 8. did:key 선택 이유 (did:ethr 대비)

**결정**: DID 방식으로 `did:key`를 사용한다. 별도 레지스트리 컨트랙트 없음.

**이유**:
- `did:ethr`는 DID Registry 컨트랙트가 필요하고, 키 회전/복구 기능을 위한 별도 인프라가 필요하다. PoC 범위를 초과한다.
- `did:key`는 P-256 공개키에서 결정론적으로 도출된다 — Passkey 공개키(x, y)가 있으면 항상 동일한 DID를 재계산할 수 있어 별도 저장소가 불필요하다.
- Passkey P-256 공개키는 등록 시 추출(`_extractP256Coords`)해 localStorage에 이미 보관하고 있어 추가 인프라 없이 DID를 즉시 파생할 수 있다.
- 형식: `did:key:z<base58btc(multicodec(0x1200) || compressed_sec1)>` — [DID Key spec](https://w3c-ccg.github.io/did-method-key/) 호환.
- 단점: 키 회전 불가. Passkey를 잃으면 DID도 사라진다. PoC 수준에서는 허용 가능.

---

## 9. VC 본문을 오프체인에 둔 이유

**결정**: VC JSON 전체는 오프체인(localStorage + 파일 교환). 온체인에는 keccak256 hash만 기록(`VCRegistry.Issued.jsonHash`).

**이유**:
- W3C VC Data Model은 본래 portable off-chain 데이터로 설계됐다. VC는 Issuer → Holder → Verifier 흐름에서 파일로 전달되는 것이 표준적이다.
- VC JSON을 온체인에 저장하면 가스비가 폭발적으로 늘어난다 (500+ bytes의 JSON을 calldata로). hash만 저장하면 `bytes32` 하나 = ~2만 gas.
- 온체인 hash로 VC 진위와 미변조 여부를 검증할 수 있으므로 trustless 원칙이 유지된다.
- 개인정보 측면에서도 VC 내용이 퍼블릭 체인에 영구 저장되지 않는다.

---

## 10. Subject DID 자기신고 모델

**결정**: `requestVc(formatId, subjectDid)` 시 요청자가 자기 DID를 calldata로 제출한다. 컨트랙트는 DID와 주소의 연결을 검증하지 않는다.

**이유**:
- `PasskeyRegistry`는 credentialIdHash → AA 주소 매핑만 보관하며 공개키 자체를 저장하지 않는다. 따라서 컨트랙트 레벨에서 "이 DID가 이 주소에 속한다"를 검증할 수 없다.
- 잘못된 DID를 제출하면 Issuer가 엉뚱한 공개키로 서명하게 되어 Holder 본인이 서명 검증을 통과할 수 없다 — 속이면 본인만 손해인 구조.
- Issuer는 오프라인으로 Requester의 DID를 확인(예: 직접 연락)한 후 승인하면 된다. PoC 수준에서 충분한 신뢰 모델.
- 향후 `PasskeyRegistry`에 pubKey를 직접 저장하거나 ZK proof로 "DID ↔ 주소" 연결을 증명하도록 확장 가능.

---

## 11. VP(Verifiable Presentation) 미구현 이유

**결정**: VC 발급까지만 구현하고 VP(Verifiable Presentation) 생성 및 검증은 구현하지 않는다.

**이유**:
- VP는 Holder가 하나 이상의 VC를 선택적으로 묶어 Verifier에게 제시하는 개념. 별도의 VP 서명 흐름, Verifier 역할, 선택 공개(selective disclosure) 로직이 필요하다.
- 이 PoC의 핵심 시연 목표는 "Passkey → DID 파생 → VC 발급 → 온체인 hash 검증"이다. VP는 그 다음 레이어.
- VC 자체는 W3C VC Data Model 1.1 호환 JSON으로 유지되므로 향후 `jwt-vp` 또는 `ldp-vp` 방식으로 VP를 추가할 수 있도록 설계됐다.
