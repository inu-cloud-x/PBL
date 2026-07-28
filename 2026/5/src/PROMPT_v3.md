# PROMPT_v3.md — DID/VC 통합

본 PoC에 W3C Decentralized Identifier(DID)와 Verifiable Credential(VC) 기능을 추가한다.
v2의 MiniENS, 투표, 메모장(DataStore) 기능은 모두 유지하며, 새 탭으로 VC 기능을 더한다.

작업은 **로컬 환경에서 완성**한 뒤 Sepolia 컨트랙트 배포 → Vercel 배포 순으로 진행한다.
내일까지 완료가 목표이므로, 결정이 막히면 본 문서의 "의사결정 가이드"를 따르고, 코드 작성 전 의문점은 사용자에게 먼저 질문할 것.

---

## 작업 원칙

- 기존 인프라(Passkey, AA 지갑, Helios, DataStore, MiniENS, VotingRegistry)는 **그대로 재사용**. 회귀 금지.
- VP(Verifiable Presentation)는 본 작업 범위 외. DID 생성 + VC 발급/조회/보관까지.
- DID는 오프체인 `did:key` 방식 — 별도 레지스트리 컨트랙트 없음. Passkey P-256 공개키에서 결정론적으로 도출.
- VC 본문은 W3C VC Data Model 1.1 호환 JSON. **온체인에는 hash만**, 본문은 오프체인(localStorage + JSON 파일 교환).
- 모든 읽기는 Helios 경유 (기존 trustless 원칙 유지). 직접 RPC fallback 금지.

---

## 시스템 설계 개요

### DID (did:key)

- Passkey 등록 시 추출한 P-256 공개키(x, y)로 결정론적 생성.
- 별도 저장 없음 — 공개키만 있으면 재계산. localStorage에 별도 키 만들지 않는다.
- 형식: `did:key:zDn...` (multicodec `0x1200` + compressed SEC1 33 bytes, base58btc with `z` prefix)
- 라이브러리: `src/lib/did.ts`

### VC 형식 (Issuer가 등록하는 템플릿)

- 필드: VC 이름 (≤40 bytes UTF-8)
- 등록 조건: **호출자가 MiniENS 이름을 보유**해야 함. 없으면 revert.
- Issuer는 자기가 등록한 형식을 비활성화(`deactivate`)할 수 있음. 비활성화된 형식은 새 요청을 받지 않으나 기존 VC는 그대로 유효.

### VC 발급 흐름

```
[1] Issuer가 형식 등록 (registerFormat)
[2] 사용자가 active 형식 목록 browse → 원하는 형식에 요청 (requestVc)
    - 이때 사용자는 자기 DID를 calldata로 함께 제출
[3] Issuer가 자기 inbox에서 요청 확인
    - 승인 (approveRequest): 세부사항 입력 → Passkey로 VC 서명
      → 컨트랙트엔 hash만 기록 → VC JSON은 .vc.json 파일로 자동 다운로드
    - 거절 (rejectRequest): 상태만 변경
[4] 수신자는 받은 .vc.json 파일을 "VC 가져오기"로 업로드
    → 컨트랙트에 기록된 hash와 일치 검증 → localStorage 저장
[5] 보관함에서 만료일(발급일 + 365d) 표시, JSON 재다운로드, 삭제 가능
```

### VC JSON 구조 (W3C VC Data Model 1.1)

```json
{
  "@context": ["https://www.w3.org/2018/credentials/v1"],
  "type": ["VerifiableCredential", "<VC 이름>"],
  "issuer": {
    "id": "did:key:<Issuer DID>",
    "name": "<Issuer MiniENS 이름>"
  },
  "issuanceDate": "<ISO8601>",
  "expirationDate": "<ISO8601 = issuanceDate + 365d>",
  "credentialSubject": {
    "id": "did:key:<Subject DID>",
    "details": "<세부사항 ≤100 bytes>"
  },
  "proof": {
    "type": "PasskeyP256Signature2026",
    "created": "<ISO8601>",
    "verificationMethod": "did:key:<Issuer DID>#key-1",
    "proofPurpose": "assertionMethod",
    "proofValue": "<base64url(P-256 raw signature, 64 bytes)>"
  }
}
```

서명 대상: `proof` 필드를 제외한 나머지를 canonical JSON(키 정렬, 공백 제거) 직렬화한 UTF-8 바이트.
서명 알고리즘: ES256 (P-256 + SHA-256). Passkey assertion으로 받는 raw signature(64 bytes) 사용.

`vcHash` (온체인 기록용): 위 canonical JSON에 `proof`까지 포함한 **완성된 VC JSON** 의 keccak256.

---

## Phase 11 — VCRegistry 컨트랙트

### 11.1 `contracts/VCRegistry.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IMiniENS {
    function reverseLookup(address owner) external view returns (string memory);
}

contract VCRegistry {
    IMiniENS public immutable ens;
    constructor(address ensAddr) { ens = IMiniENS(ensAddr); }

    struct Format {
        uint256 id;
        address issuer;
        string  name;       // ≤40 bytes
        bool    active;
        uint64  createdAt;
    }

    enum Status { Pending, Approved, Rejected }

    struct Request {
        uint256 id;
        uint256 formatId;
        address requester;
        string  subjectDid;  // 요청자 자기신고 DID
        Status  status;
        uint64  createdAt;
    }

    struct Issued {
        uint256 id;
        uint256 formatId;
        address issuer;
        address subject;
        string  details;     // ≤100 bytes
        bytes32 jsonHash;
        uint64  issuedAt;
        uint64  expiresAt;   // issuedAt + 365 days
    }

    // 함수 (필요한 것만 발췌)
    function registerFormat(string calldata name) external returns (uint256);
    function deactivateFormat(uint256 formatId) external;
    function requestVc(uint256 formatId, string calldata subjectDid) external returns (uint256);
    function approveRequest(uint256 requestId, string calldata details, bytes32 jsonHash) external returns (uint256 issuedId);
    function rejectRequest(uint256 requestId) external;

    // 조회 (페이지네이션)
    function listFormats(uint256 cursor, uint256 limit) external view returns (Format[] memory, uint256 nextCursor);
    function getRequestsByIssuer(address issuer) external view returns (Request[] memory);
    function getRequestsByRequester(address requester) external view returns (Request[] memory);
    function getIssuedToSubject(address subject) external view returns (Issued[] memory);

    // 이벤트
    event FormatRegistered(uint256 indexed id, address indexed issuer, string name);
    event FormatDeactivated(uint256 indexed id);
    event Requested(uint256 indexed id, uint256 indexed formatId, address indexed requester);
    event Approved(uint256 indexed requestId, uint256 indexed issuedId, bytes32 jsonHash);
    event Rejected(uint256 indexed requestId);
}
```

검증 규칙:
- `registerFormat`: `bytes(name).length` 1~40, `bytes(ens.reverseLookup(msg.sender)).length > 0`이어야 함.
- `requestVc`: 형식이 존재 + active. `subjectDid` 길이 ≤ 200.
- `approveRequest`: 요청 상태가 Pending, `msg.sender == formats[req.formatId].issuer`, `bytes(details).length` 1~100, `jsonHash != 0`. 발급 시 `expiresAt = issuedAt + 365 days`.
- `rejectRequest`: 요청 상태 Pending, 형식의 Issuer만.
- 재발급 허용 — 같은 (formatId, subject) 조합으로 여러 Issued가 존재할 수 있음.

### 11.2 테스트 `test/VCRegistry.t.sol`

핵심 경로만:
- ENS 미보유자가 `registerFormat` 호출 시 revert
- register → request → approve 흐름이 hash + expiresAt까지 정확히 기록되는지
- request → reject 후 같은 요청을 다시 approve할 수 없음
- 비-Issuer가 approve 시 revert
- 비활성화된 형식엔 새 요청 불가, 기존 issued는 그대로 조회됨

ENS는 mock으로 단순 stub.

### 11.3 배포 `script/DeployVC.s.sol`

- `vm.envAddress("VITE_ENS_ADDRESS")`로 MiniENS 주소 주입
- 배포 후 콘솔에 `VITE_VC_REGISTRY_ADDRESS=0x...` 출력
- broadcast 아티팩트: `broadcast/DeployVC.s.sol/11155111/run-latest.json`

---

## Phase 12 — DID 라이브러리

`src/lib/did.ts`:

```typescript
export type P256PublicKey = { x: Uint8Array; y: Uint8Array };

/** P-256 공개키 → did:key 문자열 */
export function derivePasskeyDid(pub: P256PublicKey): string;

/** did:key → verificationMethod URI */
export function didKeyId(did: string): string;  // `${did}#key-1`

/** DID document (최소 형태) */
export function didDocument(did: string, pub: P256PublicKey): JsonDidDocument;
```

구현 의존성:
- `@noble/curves` (secp256r1) — package.json에 있는지 확인. 없으면 추가.
- base58btc 인코딩: `@scure/base`의 `base58` 사용.
- multicodec prefix: P-256 public key compressed = `varint(0x1200)` = `[0x80, 0x24]`.
- compressed SEC1: `[0x02 | (y_is_odd ? 1 : 0), ...x_32bytes]` (33 bytes total)
- 최종: `'did:key:z' + base58btc(prefix || compressed)`

기존 `src/lib/passkey.ts`의 PasskeyHandle 구조에 P-256 좌표가 있으므로 그대로 사용.

---

## Phase 13 — VC 라이브러리

`src/lib/vc.ts`:

### 13.1 빌드 / 서명 / 검증

```typescript
export type VcInput = {
  vcName: string;       // ≤40 bytes
  issuerEns: string;
  issuerDid: string;
  subjectDid: string;
  details: string;      // ≤100 bytes
  issuedAt: Date;
};

export function buildVcPayload(input: VcInput): VcPayload;
export function canonicalize(obj: unknown): string;  // 키 정렬 + 공백 제거
export async function signVc(payload: VcPayload, passkey: PasskeyHandle): Promise<VerifiableCredential>;
export async function verifyVcSignature(vc: VerifiableCredential): Promise<boolean>;
export function isExpired(vc: VerifiableCredential, now?: Date): boolean;
export function vcHash(vc: VerifiableCredential): `0x${string}`;  // keccak256
```

`signVc`의 흐름:
1. `canonicalize(payload)` → UTF-8 bytes
2. `navigator.credentials.get()` 호출 — `challenge`에 canonical bytes의 SHA-256, `allowCredentials`에 issuer Passkey의 credentialId
3. assertion에서 받은 signature는 DER 인코딩이므로 raw r||s (64 bytes)로 변환
4. proof를 채워 VC 완성

`verifyVcSignature`:
- `proof.verificationMethod`에서 issuer DID 추출 → 공개키 복원
- `@noble/curves` p256으로 검증
- 만료는 별도 함수 `isExpired`로 — 검증은 서명만, 만료는 정책

### 13.2 localStorage 보관

```typescript
const KEY = (chainId: number, hash: string) => `vc:${chainId}:${hash}`;

export function saveVc(vc: VerifiableCredential, chainId: number): string;  // returns hash
export function loadAllVcs(chainId: number): VerifiableCredential[];
export function removeVc(chainId: number, hash: string): void;
export function exportVcAsJson(vc: VerifiableCredential): { filename: string; blob: Blob };
export async function importVcFromFile(file: File): Promise<VerifiableCredential>;
```

`exportVcAsJson` 파일명: `<sanitized vcName>-<short subject addr or DID>-<short hash>.vc.json`

### 13.3 컨트랙트 연동 함수

```typescript
// 쓰기 (AA client 경유)
export async function registerFormat(client, name: string): Promise<TxHash>;
export async function deactivateFormat(client, formatId: bigint): Promise<TxHash>;
export async function requestVc(client, formatId: bigint, subjectDid: string): Promise<TxHash>;
export async function approveRequest(client, requestId: bigint, details: string, hash: `0x${string}`): Promise<TxHash>;
export async function rejectRequest(client, requestId: bigint): Promise<TxHash>;

// 읽기 (Helios 경유)
export async function listFormats(helios, opts?: { onlyActive?: boolean }): Promise<Format[]>;
export async function listIncomingRequests(helios, issuer: Address): Promise<Request[]>;
export async function listOutgoingRequests(helios, requester: Address): Promise<Request[]>;
export async function listIssuedToMe(helios, subject: Address): Promise<Issued[]>;
```

`listFormats`는 컨트랙트 페이지네이션 사용. 클라이언트는 cursor를 끝까지 돌려 active만 반환.

---

## Phase 14 — VC 형식 게시판 UI

`src/components/vc/FormatBoard.tsx`:

- 상단 카드: **새 형식 등록**
  - 내 ENS 이름 조회(`useENSName(myAddress)`) — 없으면 "ENS 이름 등록 후 가능" 안내 + 버튼 비활성
  - VC 이름 입력 (≤40 bytes UTF-8 카운터)
  - "등록" 버튼 → `registerFormat`
- 하단: **전체 active 형식 목록**
  - 카드별: VC 이름, Issuer ENS 이름(역조회 캐시), 등록일
  - 각 카드 하단 두 버튼:
    - 내가 Issuer인 경우: "비활성화"
    - 아닌 경우: "이 형식 요청하기" → RequestPanel로 이동
- 페이지 진입 시 `listFormats({ onlyActive: true })` 호출, Helios 상태 표시 (ProposalList 패턴 그대로).

---

## Phase 15 — VC 요청 UI

`src/components/vc/RequestPanel.tsx`:

- 요청 모달 (FormatBoard에서 진입):
  - 형식 이름, Issuer ENS 표시
  - 안내문: "요청 시 본인의 DID가 Issuer에게 전달됩니다."
  - "요청" 버튼 → `derivePasskeyDid(myPasskey.publicKey)` → `requestVc(formatId, subjectDid)`
  - 성공 시 "내 요청" 섹션으로 이동

`src/components/vc/MyRequests.tsx`:

- `listOutgoingRequests(myAddress)` 호출
- 정렬: createdAt DESC
- 각 행: 형식 이름 / Issuer ENS / 상태 배지 (대기 / 승인 / 거절) / 시각
- 우측 상단 "새로고침" 버튼 — 사용자 액션 폴링
- 승인된 요청 옆엔 "VC 받기 안내" 안내문구만 (Issuer가 직접 .vc.json 파일 전달해야 함을 명시)

---

## Phase 16 — Issuer Inbox UI

`src/components/vc/IssuerInbox.tsx`:

- `listIncomingRequests(myAddress)` 중 **Pending만** 표시
- 각 행: 요청자 주소(ENS 있으면 이름), 형식 이름, subjectDid 일부, 시각, "승인" / "거절" 버튼

### 승인 모달 흐름

1. 세부사항 입력 (≤100 bytes UTF-8 카운터)
2. "발급" 클릭 시:
   ```
   a. 내 Passkey 공개키 → issuerDid 도출
   b. 내 ENS 이름 조회 (issuerEns)
   c. buildVcPayload({ ...formatName, issuerEns, issuerDid, subjectDid: request.subjectDid, details, issuedAt: new Date() })
   d. signVc(payload, myPasskey)  // navigator.credentials.get() 한 번 더 필요
   e. hash = vcHash(vc)
   f. approveRequest(requestId, details, hash) — 온체인
   g. saveVc(vc, chainId) — Issuer 본인 localStorage에도 백업
   h. exportVcAsJson(vc) → 자동 다운로드 트리거
   i. 모달에 "이 파일을 요청자에게 직접 전달하세요" 안내 + 재다운로드 버튼
   ```
3. 거절은 `rejectRequest(requestId)` 호출만, 별도 입력 없음. 확인 다이얼로그만.

**주의**:
- step (d)에서 Passkey assertion이 한 번 더 필요한데, 이게 Issuer 입장에서 UX 저하 요인. 사용자에게 "발급을 위해 지문 인증이 한 번 더 필요합니다" 안내 명시.
- step (f)와 (d) 사이의 race condition — 서명까지 했는데 온체인 호출이 실패하면 hash는 있지만 발급 기록은 없음. 이때 사용자에게 재시도 가능하게 retry 버튼.

---

## Phase 17 — 내 VC 보관함

`src/components/vc/MyCredentials.tsx`:

상단: **VC 가져오기**
- 파일 선택 input (`accept=".vc.json,application/json"`)
- 업로드 시:
  ```
  1. importVcFromFile(file) → VC 객체
  2. verifyVcSignature(vc) — 실패 시 reject + 사용자에게 사유 표시
  3. hash = vcHash(vc), subject = vc.credentialSubject.id에서 주소 추출 불가
     → 대신: listIssuedToMe(myAddress)에서 hash가 일치하는 Issued 찾기
     → 못 찾으면 "이 VC가 내 주소로 발급된 기록이 없습니다" 거부
  4. saveVc(vc, chainId)
  5. 목록 새로고침
  ```

하단: **내 VC 목록**
- `loadAllVcs(chainId)` 표시
- 각 카드:
  - VC 이름 (큰 글자)
  - Issuer ENS / Issuer DID 짧게
  - 발급일 / 만료일 (만료 시 빨간 배지 "EXPIRED")
  - 세부사항
  - 액션: "JSON 다운로드", "삭제", "온체인 검증" (hash 매칭 결과를 토스트)

**중요 — credentialSubject.id에 주소 정보가 없음**:
- DID는 공개키 기반이라 주소를 역추적 불가
- 따라서 "import 시 본인 발급 기록과 매칭" 검증은 `listIssuedToMe(myAddress)`의 hash들과 비교
- 만약 이 매칭이 실패하면 다른 사람에게 발급된 VC를 잘못 import한 것 → reject

---

## Phase 18 — Nav 통합, 환경변수, 배포

### 18.1 Nav

`src/components/Nav.tsx`에 최상위 탭 추가:
```
[ 데이터 ] [ ENS 이름 ] [ 투표 ] [ VC ]
```

VC 탭 내부 sub-nav:
```
[ 형식 게시판 ] [ 받은 요청 ] [ 내 요청 ] [ 내 보관함 ]
```

### 18.2 환경변수

`src/config.ts`:
```typescript
VITE_VC_REGISTRY_ADDRESS  // 필수 (getMissingEnvKeys에 추가)
```

`.env.example` 업데이트, `vercel.json`의 env 매핑도 확인.

### 18.3 문서 업데이트

`CLAUDE.md`:
- 배포 컨트랙트 표에 `VCRegistry` 추가
- 핵심 파일 위치에 `src/lib/did.ts`, `src/lib/vc.ts`, `src/components/vc/*` 추가
- 알려진 제약사항에 항목 추가:
  - "VC import 시 본인 발급 기록과 hash 매칭 필요 — 다른 주소로 발급된 VC는 import 거부"
  - "Issuer 승인 시 Passkey assertion이 한 번 더 필요"

`DECISIONS.md` 새 항목:
- **§8 — did:key 선택 이유** (did:ethr 대비 레지스트리 컨트랙트 불필요, 시간 제약)
- **§9 — VC 본문을 오프체인에 둔 이유** (가스 효율, W3C VC가 본래 오프체인 portable 데이터)
- **§10 — Subject DID 자기신고 모델** (PasskeyRegistry는 공개키를 직접 보관 안 함 → request 시 요청자가 자기 DID를 calldata로 제출, 잘못 적으면 본인만 손해)
- **§11 — VP 미구현 이유** (PoC 범위 + 시간 제약. 향후 jwt-vp 또는 LDP-VP로 확장 가능하도록 VC 자체는 W3C 호환 형태로 유지)

### 18.4 배포 순서

```bash
# 1) 로컬 통합 테스트 (별도 브라우저 두 개로 Issuer/Requester 시뮬레이션)
npm run dev
# 체크리스트: 본 문서 맨 아래 "완료 기준" 참조

# 2) 컨트랙트 배포 (env: PRIVATE_KEY, RPC_URL, VITE_ENS_ADDRESS)
forge build
forge script script/DeployVC.s.sol --rpc-url $RPC_URL --broadcast --private-key $PRIVATE_KEY

# 3) Vercel 환경변수에 VITE_VC_REGISTRY_ADDRESS 추가

# 4) git
git add .
git commit -m "feat(v3): DID/VC integration — format registry, request/approve flow, credential vault"
git tag v3-did-vc

# 5) Vercel 배포 (자동) 후 프로덕션에서 동일 흐름 재현
```

---

## 의사결정 가이드 (시간 부족 시)

**우선순위 (위에서부터 깎아냄)**:
1. Phase 11~13 — 컨트랙트 + 라이브러리 (모든 기능의 토대)
2. Phase 16 + 17 — Issuer 승인 + 내 보관함 (시연 가능한 최소 단위)
3. Phase 14 + 15 — 형식 게시판 + 요청 UI
4. Phase 18 — Nav 통합 + 배포

배포 단계(18)는 **항상 마지막에**, 단 다른 모든 것을 완성한 뒤가 아니라 **Phase 16~17까지 작동하면 일단 배포** 후 14~15 추가 배포도 OK.

**막혔을 때**:
- 컨트랙트 함수 시그니처가 헷갈리면 단순화. `getRequestsByIssuer`가 너무 비싸면 `requestIds[]`만 반환하고 클라이언트가 개별 조회.
- WebAuthn assertion에서 raw signature 추출이 막히면 `@simplewebauthn/server`의 helper 또는 직접 DER 파싱(`@noble/curves`의 `Signature.fromDER`).
- canonicalize에서 부동소수점/유니코드 이슈가 의심되면 `json-canonicalize` 또는 RFC 8785(JCS) 라이브러리 사용 검토. 단, payload에 float 없음이 보장되면 직접 구현으로 충분.
- 무엇이든 의문점이 있으면 코드 작성 전 사용자에게 먼저 질문.

**회귀 방지**:
- 새 코드는 모두 `src/lib/did.ts`, `src/lib/vc.ts`, `src/components/vc/*`, `contracts/VCRegistry.sol`, `script/DeployVC.s.sol`, `test/VCRegistry.t.sol`에 격리.
- 기존 파일 수정은 `src/components/Nav.tsx`, `src/config.ts`, `.env.example`, `CLAUDE.md`, `DECISIONS.md`만 허용.
- 기존 ENS / 투표 / DataStore 코드는 건드리지 않는다.

---

## 완료 기준 (Definition of Done)

로컬 환경에서 다음이 모두 성공해야 함:

- [ ] VCRegistry 컨트랙트 Sepolia 배포 완료, 주소 `.env` + `CLAUDE.md` 등록
- [ ] Issuer가 ENS 이름 없이 형식 등록 시도 시 revert 확인
- [ ] Issuer가 형식 등록 → 다른 사용자가 요청 → Issuer 승인 → `.vc.json` 자동 다운로드까지 흐름 작동
- [ ] 다운로드된 `.vc.json`을 수신자가 다른 브라우저(다른 Passkey)에서 import 시:
  - 서명 검증 통과
  - 온체인 hash 매칭 통과
  - 보관함에 표시됨
- [ ] 다른 주소로 발급된 VC를 import 시도 시 거부
- [ ] 거절 흐름 — Issuer가 reject 후 같은 요청 재승인 불가
- [ ] 만료일 표시 (발급일 + 365d), 미래 시각으로 강제 변경 테스트로 EXPIRED 배지 노출 확인
- [ ] 기존 기능 회귀 없음:
  - 메모장(DataStore) store/getAll 정상
  - MiniENS register/resolve/reverseLookup 정상
  - 투표 생성/조회/투표 정상
- [ ] Vercel 배포 후 프로덕션 URL에서 위 흐름 전체 재현
- [ ] `CLAUDE.md` / `DECISIONS.md` 업데이트 커밋
- [ ] git tag `v3-did-vc`