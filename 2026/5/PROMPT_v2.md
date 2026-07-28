# 탈중앙화 dApp PoC 확장 — 거버넌스 + 미니 ENS

> Claude Code 작업 지시 문서. 진행 전 본 문서를 처음부터 끝까지 읽고, `CLAUDE.md`와 `DECISIONS.md`를 함께 확인한 뒤 시작할 것. 모호한 점이 있으면 코드를 작성하기 전에 먼저 질문할 것.

---

## 1. 작업 범위

Phase 1~5(기존 PoC)에서 구현된 인프라 위에 두 가지 dApp을 추가한다:

1. **MiniENS** — 스마트 컨트랙트 기반 이름 레지스트리. AA 지갑 주소에 사람이 읽기 좋은 이름을 매핑한다.
2. **익명 투표 / 거버넌스** — 제안 생성·투표·결과 조회. 투표 결과에 0x 주소 대신 ENS 이름을 표시한다.

MiniENS는 두 dApp 사이의 **신원 레이어**다. 투표 컴포넌트는 MiniENS에서 이름을 가져와 표시하고, MiniENS가 없는 주소는 축약된 0x 주소로 fallback한다.

**절대 건드리지 않는 것:**
- `contracts/PasskeyRegistry.sol`, `contracts/DataStore.sol`, `contracts/coinbase/`
- `src/lib/passkey.ts`, `src/lib/helios.ts`, `src/lib/wallet.ts` (기존 인터페이스)
- `api/beacon-proxy.ts`
- 기존 환경변수 키

---

## 2. 추가 기능 요구사항

### MiniENS
1. **Register** — AA 지갑 주소에 이름(3~32자)을 등록한다. 주소당 하나, 선착순, 양도 불가.
2. **Release** — 자신의 이름 등록을 해제한다. 해제 후 즉시 재등록 가능.
3. **Resolve** — 이름 → 주소 조회 (Helios 검증).
4. **Reverse lookup** — 주소 → 이름 조회 (Helios 검증).

### 거버넌스 투표
1. **Create proposal** — 제목(최대 100 bytes)과 설명(최대 500 bytes), 투표 기간을 지정해 제안을 올린다.
2. **Vote** — 열린 제안에 Yes / No / Abstain 중 하나를 투표한다. 주소당 한 번.
3. **View results** — 마감 시간, 현재 집계, 제안자·투표자 이름(MiniENS)을 Helios로 검증해 표시한다.

> **익명성 범위:** 온체인 완전 익명(ZK proof)은 이 PoC의 범위를 벗어난다. 투표는 AA 지갑 주소에 묶인 가명(pseudonymous) 방식으로 처리하되, UI에서 ENS 이름으로 표시해 원시 주소를 감춘다. 이 결정은 `DECISIONS.md`에 추가한다.

---

## 3. 추가 기술 스택

기존 스택은 그대로 유지한다. 추가되는 항목만 기록한다.

| 영역 | 선택 | 비고 |
|---|---|---|
| 라우팅 | 탭 기반 상태 (`useState`) | react-router 도입 금지 — SPA 단순성 유지 |
| 이름 캐시 | `Map<string, string>` 인메모리 | 세션 내 재조회 최소화 |
| 시간 표시 | 브라우저 `Intl.DateTimeFormat` | 외부 라이브러리 금지 |

---

## 4. 추가 환경변수

기존 `.env.example`에 아래를 추가한다. 코드에 하드코딩하지 않는다.

```env
# MiniENS 컨트랙트 주소 (forge script DeployENS 실행 후 기입)
VITE_MINI_ENS_ADDRESS=

# VotingRegistry 컨트랙트 주소 (forge script DeployVoting 실행 후 기입)
VITE_VOTING_REGISTRY_ADDRESS=
```

두 값이 비어 있으면 앱은 해당 탭을 "컨트랙트 미배포" 상태로 표시하고, mock으로 우회하지 않는다.

---

## 5. 스마트 컨트랙트

### 5-1. MiniENS

```solidity
// contracts/MiniENS.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MiniENS {
    mapping(bytes32 => address) private _nameToAddr;  // keccak256(name) → AA 주소
    mapping(address => string)  private _addrToName;  // AA 주소 → 이름

    event Registered(bytes32 indexed nameHash, string name, address indexed owner);
    event Released(bytes32 indexed nameHash, address indexed owner);

    /// 3~32자, 소문자 알파벳·숫자·하이픈만 허용. 첫/끝 글자는 하이픈 금지.
    function register(string calldata name) external {
        bytes32 h = _validate(name);
        require(_nameToAddr[h] == address(0), "name taken");
        require(bytes(_addrToName[msg.sender]).length == 0, "already has name");
        _nameToAddr[h] = msg.sender;
        _addrToName[msg.sender] = name;
        emit Registered(h, name, msg.sender);
    }

    function release() external {
        string memory name = _addrToName[msg.sender];
        require(bytes(name).length > 0, "no name registered");
        bytes32 h = keccak256(bytes(name));
        delete _nameToAddr[h];
        delete _addrToName[msg.sender];
        emit Released(h, msg.sender);
    }

    function resolve(string calldata name) external view returns (address) {
        return _nameToAddr[keccak256(bytes(name))];
    }

    function reverseLookup(address addr) external view returns (string memory) {
        return _addrToName[addr];
    }

    function _validate(string calldata name) internal pure returns (bytes32) {
        bytes memory b = bytes(name);
        require(b.length >= 3 && b.length <= 32, "length 3-32");
        require(b[0] != '-' && b[b.length - 1] != '-', "no leading/trailing hyphen");
        for (uint256 i; i < b.length; i++) {
            bytes1 c = b[i];
            bool ok = (c >= 0x61 && c <= 0x7a)   // a-z
                   || (c >= 0x30 && c <= 0x39)   // 0-9
                   || c == 0x2d;                 // -
            require(ok, "invalid char");
        }
        return keccak256(b);
    }
}
```

### 5-2. VotingRegistry

```solidity
// contracts/VotingRegistry.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract VotingRegistry {
    enum Choice { Yes, No, Abstain }

    struct Proposal {
        address creator;
        string  title;          // 최대 100 bytes
        bytes   description;    // 최대 500 bytes
        uint64  deadline;       // block.timestamp 기준 Unix 초
        uint128 yesVotes;
        uint128 noVotes;
        uint128 abstainVotes;
    }

    uint256 public proposalCount;
    mapping(uint256 => Proposal)                     public proposals;
    mapping(uint256 => mapping(address => bool))     public hasVoted;

    uint256 public constant MIN_DURATION = 1 hours;
    uint256 public constant MAX_DURATION = 30 days;

    event ProposalCreated(uint256 indexed id, address indexed creator, string title, uint64 deadline);
    event VoteCast(uint256 indexed proposalId, address indexed voter, Choice choice);

    function createProposal(
        string  calldata title,
        bytes   calldata description,
        uint256 duration
    ) external {
        require(bytes(title).length > 0 && bytes(title).length <= 100, "title 1-100 bytes");
        require(description.length <= 500, "desc max 500 bytes");
        require(duration >= MIN_DURATION && duration <= MAX_DURATION, "invalid duration");

        uint256 id = proposalCount++;
        proposals[id] = Proposal({
            creator:      msg.sender,
            title:        title,
            description:  description,
            deadline:     uint64(block.timestamp + duration),
            yesVotes:     0,
            noVotes:      0,
            abstainVotes: 0
        });
        emit ProposalCreated(id, msg.sender, title, uint64(block.timestamp + duration));
    }

    function vote(uint256 proposalId, Choice choice) external {
        Proposal storage p = proposals[proposalId];
        require(p.deadline > 0, "proposal not found");
        require(block.timestamp < p.deadline, "voting closed");
        require(!hasVoted[proposalId][msg.sender], "already voted");

        hasVoted[proposalId][msg.sender] = true;
        if      (choice == Choice.Yes)     p.yesVotes++;
        else if (choice == Choice.No)      p.noVotes++;
        else                               p.abstainVotes++;
        emit VoteCast(proposalId, msg.sender, choice);
    }

    function getProposal(uint256 id) external view returns (Proposal memory) {
        return proposals[id];
    }
}
```

**주의:** `msg.sender`는 AA 스마트 지갑 주소다. ENS 이름도, 투표 기록도 모두 AA 주소 기준이다.

---

## 6. 알려진 함정과 처리 방침

- **이름 정규화:** 컨트랙트는 소문자만 허용한다. 프론트엔드에서 입력값을 `name.toLowerCase()`로 변환한 뒤 전송해야 한다. 대소문자 혼용 입력을 무음으로 변환하지 말고 UI에서 "소문자로 변환됨" 안내를 표시한다.
- **Helios 준비 선행:** MiniENS와 VotingRegistry의 모든 읽기 경로는 `initHelios()`가 완료된 후에만 호출한다. 기존 `helios.ts`의 싱글턴 패턴을 그대로 사용하고, 별도 Helios 인스턴스를 만들지 않는다.
- **ENS 캐시 무효화:** `register`/`release` 트랜잭션이 성공하면 해당 주소의 캐시 항목을 즉시 삭제한다. 캐시를 낙관적으로 갱신하면 Helios 검증을 우회하는 것과 같다.
- **투표 마감 시간 표시:** `block.timestamp`는 채굴자가 ±15초 조작할 수 있다. PoC 수준에서는 허용하되, UI에 "마감 시간은 블록 타임스탬프 기준으로 약 15초 오차가 있을 수 있습니다"를 표시한다.
- **제안 페이지네이션:** `proposalCount`가 커지면 전체 조회 비용이 증가한다. 현재는 최신 20개만 가져오도록 제한한다(`proposalCount - 1`부터 역순 20개). 무제한 조회를 구현하지 않는다.
- **Description 인코딩:** `bytes calldata description`은 UTF-8 인코딩된 텍스트다. 프론트에서 `new TextEncoder().encode(text)`로 변환한다. `datastore.ts`의 패턴과 동일하다.
- **AA 지갑 미보유 사용자:** PasskeyRegistry에 등록되지 않은 주소는 ENS 역방향 조회 결과가 빈 문자열이다. 이 경우 `0x1234…abcd` 형태로 축약 표시한다. null/undefined를 UI에 그대로 노출하지 않는다.

---

## 7. 디렉터리 구조 (추가·변경 부분만)

```
.
├─ contracts/
│  ├─ MiniENS.sol                    # 신규
│  └─ VotingRegistry.sol             # 신규
├─ script/
│  ├─ DeployENS.s.sol                # 신규
│  └─ DeployVoting.s.sol             # 신규
└─ src/
   ├─ lib/
   │  ├─ ens.ts                      # 신규 — register/release/resolve/reverseLookup
   │  └─ voting.ts                   # 신규 — createProposal/vote/getProposals
   ├─ hooks/
   │  └─ useENSName.ts               # 신규 — address → name, 인메모리 캐시
   └─ components/
      ├─ Nav.tsx                      # 신규 — 탭 내비게이션 (DataStore / ENS / 투표)
      ├─ ENSRegistrar.tsx             # 신규 — 이름 등록·해제·조회
      ├─ ProposalList.tsx             # 신규 — 최신 20개 제안 목록
      ├─ ProposalCard.tsx             # 신규 — 제안 요약 + 투표 버튼
      ├─ CreateProposal.tsx           # 신규 — 제안 생성 폼
      └─ VotePanel.tsx                # 신규 — Yes/No/Abstain 선택 + 결과 바 차트
```

`App.tsx`는 탭 상태를 관리하고 `Nav.tsx`를 렌더링한다. 기존 DataEditor·DataViewer는 첫 번째 탭("데이터")에 그대로 유지한다.

---

## 8. 구현 단계

각 Phase는 별도 커밋으로 분리하고, 끝날 때마다 동작을 확인한 뒤 다음으로 넘어간다. Phase 단위로 보고할 것.

### Phase 6 — MiniENS 컨트랙트

- `contracts/MiniENS.sol` 작성 (§5-1의 코드 기반)
- `test/MiniENS.t.sol` Forge 테스트:
  - register 성공, 중복 등록 거부, 잘못된 문자 거부
  - release 후 재등록 가능
  - resolve / reverseLookup 정확성
- `script/DeployENS.s.sol` 작성 — 주소를 콘솔에 출력하고 `.env` 변수 힌트 제공
- `forge build` 경고 없음

**검증:** `forge test --match-path test/MiniENS.t.sol -v` 전체 통과.

---

### Phase 7 — MiniENS 프론트엔드

- `src/config.ts`에 `miniEnsAddress` 항목 추가 (optional)
- `src/lib/ens.ts` 작성:
  - `ensRegister(client, name)` — AA 경유 writeContract
  - `ensRelease(client)` — AA 경유 writeContract
  - `ensResolve(name)` — Helios 클라이언트로 readContract
  - `ensReverseLookup(address)` — Helios 클라이언트로 readContract
- `src/hooks/useENSName.ts` 작성:
  - 인자: `address | undefined`
  - 반환: `string | undefined` (이름 또는 undefined)
  - `Map<address, name>` 인메모리 캐시, Helios ready 후 조회
- `src/components/ENSRegistrar.tsx` 작성:
  - 현재 내 이름 표시 (있으면 해제 버튼, 없으면 등록 폼)
  - 이름 입력 시 소문자 변환 안내 표시
  - 트랜잭션 전송 후 캐시 무효화
- `App.tsx`에 탭 내비게이션 추가 (DataStore / ENS / 투표). 투표 탭은 "Coming in Phase 9" 플레이스홀더.

**검증:** 새 이름 등록 → 페이지 새로고침 후 내 이름 Helios 조회로 복원 → release → 재등록.

---

### Phase 8 — VotingRegistry 컨트랙트

- `contracts/VotingRegistry.sol` 작성 (§5-2의 코드 기반)
- `test/VotingRegistry.t.sol` Forge 테스트:
  - 제안 생성 성공, 제목/설명 길이 초과 거부
  - duration 범위 밖 거부 (MIN_DURATION 미만, MAX_DURATION 초과)
  - 투표 성공 (Yes/No/Abstain 각각)
  - 마감 후 투표 거부
  - 중복 투표 거부
- `script/DeployVoting.s.sol` 작성
- `forge build` 경고 없음

**검증:** `forge test --match-path test/VotingRegistry.t.sol -v` 전체 통과.

---

### Phase 9 — 투표 프론트엔드

- `src/config.ts`에 `votingRegistryAddress` 항목 추가 (optional)
- `src/lib/voting.ts` 작성:
  - `votingCreate(client, title, description, durationSecs)` — AA 경유 writeContract
  - `votingVote(client, proposalId, choice)` — AA 경유 writeContract
  - `votingGetProposal(id)` — Helios readContract
  - `votingGetRecent(count)` — proposalCount에서 역순으로 최대 `count`개 조회
- `src/components/ProposalList.tsx` 작성:
  - 최신 20개 목록. 마감 여부에 따라 "진행 중" / "종료" 배지 표시.
  - 제안자 주소를 `useENSName`으로 조회해 이름이 있으면 이름 표시.
- `src/components/ProposalCard.tsx` 작성:
  - 제목, 설명, 마감 시간, Yes/No/Abstain 집계 표시.
  - 비율 바 차트 (CSS width만 사용, 외부 차트 라이브러리 금지).
- `src/components/CreateProposal.tsx` 작성:
  - 제목(100 bytes 카운터), 설명(500 bytes 카운터), 기간 입력(시간 단위).
- `src/components/VotePanel.tsx` 작성:
  - 이미 투표했으면 내 선택 표시. 마감됐으면 버튼 비활성.
- 투표 탭에 `ProposalList` + `CreateProposal` 렌더링.

**검증:** 제안 생성 → Helios로 목록 조회 확인 → 투표 → 집계 반영 확인 → 마감 후 투표 시도 시 컨트랙트에서 거부.

---

### Phase 10 — 통합·정리·재배포

- `DECISIONS.md`에 항목 추가: "익명 투표의 범위 — ZK 제외, 가명 방식 선택 이유"
- 기존 `DataViewer.tsx`에서 항목 작성자 주소(= `client.account.address`)를 `useENSName`으로 표시하도록 수정.
- `getMissingEnvKeys()`에 `VITE_MINI_ENS_ADDRESS`, `VITE_VOTING_REGISTRY_ADDRESS` 추가 (단, 선택 키로 — 없어도 앱은 시작됨).
- Sepolia에 `MiniENS`와 `VotingRegistry` 배포:
  ```bash
  forge script script/DeployENS.s.sol --rpc-url $RPC_URL --broadcast --private-key $PRIVATE_KEY
  forge script script/DeployVoting.s.sol --rpc-url $RPC_URL --broadcast --private-key $PRIVATE_KEY
  ```
- Vercel 환경변수에 두 주소 추가 후 프로덕션 배포.
- `CLAUDE.md`의 컨트랙트 주소 표에 새 항목 추가.

**검증:** 프로덕션 URL에서 전체 플로우 확인 — Passkey 로그인 → ENS 이름 등록 → 제안 생성 → 투표 → 결과에서 ENS 이름 표시.

---

## 9. 작업 규칙

- 각 Phase 끝에 동작 결과(터미널 출력 또는 화면 설명)와 함께 보고 후 다음으로 진행.
- 기존 `lib/helios.ts`의 싱글턴을 변경하지 않는다. 새 dApp에서 Helios가 필요하면 `initHelios()` / `createHeliosClient()`를 그대로 호출한다.
- ENS 조회 실패(컨트랙트 미배포, Helios 미동기화)는 UI에 명시적으로 표시한다. 빈 문자열이나 undefined를 조용히 무시하지 않는다.
- 투표 읽기 경로에서 raw RPC fallback을 만들지 않는다. Helios가 준비되기 전에는 "동기화 중" 상태를 표시한다.
- 컴포넌트에서 직접 `createHeliosClient()`를 호출하지 않는다. lib 함수(`ens.ts`, `voting.ts`)에서만 호출한다.
- react-router, 외부 차트 라이브러리, date-fns 등 새로운 런타임 의존성을 추가하지 않는다. 필요하다면 추가 전에 먼저 사유를 보고한다.

Phase 6부터 시작.
