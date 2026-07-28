# T2C-Prov System Technical Specification

본 문서는 **T2C-Prov (Provenance-Anchored Text-to-CadQuery Generation Audit Chain)** 시스템의 아키텍처, 워크플로우 및 핵심 유사도 메트릭(Metric)의 기술적 상세 내용을 기술합니다.

---

## 1. 시스템 개요 (System Overview)

T2C-Prov는 AI 모델(`ricemonster/qwen2.5-3B-SFT`)이 생성한 CAD 아티팩트의 출처(Provenance)를 증명하고, 블록체인 상에서 위변조를 감사(Audit)하기 위한 시스템입니다.

### 핵심 구성 요소
- **Generation Engine**: HuggingFace Transformers 및 Apple MPS 가속 기반의 CAD 스크립트 생성.
- **Storage (IPFS)**: 생성된 원본 파일(Script, STEP, STL)을 분산 저장하여 불변의 주소(CID) 확보.
- **Trust Anchor (Blockchain)**: Hardhat 기반 스마트 컨트랙트(`Registry.sol`)에 지문(Hash)과 메타데이터 기록.
- **Audit Engine**: 생성물 간의 유사성을 4개 레이어로 분석하여 중복 및 변조 탐지.

---

## 2. 통합 워크플로우 (End-to-End Workflow)

`python -m t2c_prov.cli.generate --prompt "..." --register` 명령어 실행 시 다음 단계가 자동 수행됩니다.

1.  **Inference**: 모델이 프롬프트를 해석하여 CadQuery Python 코드를 생성.
2.  **Cleaning**: `DataFlowSimplifier` 및 AST 정규화를 통해 실행 가능한 순수 코드로 정제.
3.  **Export**: 정제된 코드를 실행하여 3D 모델 파일(`model.step`, `model.stl`) 생성.
4.  **Hashing**: 아티팩트의 다층 지문(Multi-layer Hash) 계산.
5.  **IPFS Pinning**: 생성된 폴더 전체를 IPFS에 업로드하고 폴더 CID 획득.
6.  **On-chain Anchoring**: CID와 해시값들을 블록체인에 `register` 트랜잭션으로 기록.

---

## 3. 다층 해싱 전략 (Multi-Layer Hashing)

블록체인에 등록되는 3가지 핵심 지문은 다음과 같습니다.

### 3.1 Prompt Hash (Strict Equality)
- **목적**: 입력 문장의 고유성 확인.
- **방식**: 
  - **Unicode NFKC 정규화**: `unicodedata.normalize("NFKC", text)`를 사용합니다. 한국어나 특수문자의 경우, 컴퓨터가 글자를 저장하는 방식(예: '가'를 통짜로 저장하느냐, 'ㄱ'+'ㅏ'로 풀어서 저장하느냐, 혹은 전각/반각 차이)이 다를 수 있습니다. NFKC는 이를 가장 표준적인 형태(호환성 분해 후 정준 결합)로 통일하여, 눈에 똑같이 보이는 글자가 다른 해시를 갖는 것을 방지합니다.
  - **소문자 변환**: 대소문자 차이를 무시합니다 (`text.lower()`).
  - **연속 공백 제거**: 정규식 `re.sub(r"\s+", " ", text).strip()`을 사용하여, 단어 사이의 띄어쓰기가 2칸이든 3칸이든 모두 1칸으로 통일하고, 문장 앞뒤의 여백을 완전히 제거합니다.
  - 이후 `hashlib.sha256`을 적용하여 최종 바이트 지문을 만듭니다.

### 3.2 Script Hash (Canonical AST)
- **목적**: 스타일(공백, 주석)과 상관없이 기능이 같으면 동일한 해시 생성 (Alpha-Equivalence).
- **방식**:
  - **AST 파싱**: Python 코드를 단순 텍스트가 아닌 **추상 구문 트리(Abstract Syntax Tree)**라는 구조 데이터로 변환합니다 (`ast.parse()`). 이렇게 하면 띄어쓰기나 엔터 같은 시각적 요소가 모두 사라지고 뼈대만 남습니다.
  - **도큐먼트 스트링 제거 (`StripDocstrings`)**: 코드 실행에 영향을 주지 않는 문자열(예: `"""설명"""`) 노드를 트리를 순회하며 강제로 삭제합니다.
  - **데이터 흐름 단순화 (`DataFlowSimplifier`)**: `my_box = cq.Workplane().box(10); result = my_box` 처럼 변수를 한 번 거쳐서 `result`에 넣는 코드를 추적하여, `result = cq.Workplane().box(10)`으로 트리 구조를 직접 수정(Inlining)합니다.
  - **변수명 알파-리네이밍 (`NormalizeVariables`)**: 사용자가 지은 변수명(`my_box`, `cylinder` 등)을 등장 순서대로 `_v0`, `_v1` 등으로 일괄 치환합니다.
  - **Black 포맷팅**: 변환된 트리를 다시 코드로 되돌린 후(`ast.unparse()`), 파이썬 표준 포맷터인 `black`을 사용해 줄바꿈 규격(88자 제한 등)을 완벽히 통일합니다.
  - 이 통일된 문자열을 SHA-256으로 해싱합니다.

### 3.3 Geometry Hash (Combinatorial Signature)
- **목적**: 모델링 방식이 달라도 결과 형상이 같으면 동일한 해시 생성.
- **방식**: `build123d` 라이브러리로 STEP 파일을 읽어들여 3D 형상에서 7가지 수학적 특징(7-tuple)을 뽑아내어 조합합니다.
  1. `n_faces`: 다각형 면의 개수
  2. `n_edges`: 모서리의 개수
  3. `n_vertices`: 꼭짓점의 개수
  4. `sqrt(area)`: 표면적의 제곱근 (스케일 불변성을 위해 소수점 6자리 반올림)
  5. `volume ** (1/3)`: 부피의 세제곱근 (소수점 6자리 반올림)
  6. `ratio_xz`: 바운딩 박스의 X축 대비 Z축 비율 (소수점 6자리 반올림)
  7. `ratio_yz`: 바운딩 박스의 Y축 대비 Z축 비율 (소수점 6자리 반올림)
  - 이 7개의 숫자를 C언어 구조체 바이트 배열(`struct.pack("<3I4d", ...)`)로 압축한 뒤 SHA-256 해시를 뜹니다. 이렇게 하면 코드가 완전히 달라도 결과물의 크기와 형태가 같으면 동일한 해시가 나옵니다.

---

## 4. 4단계 유사도 메트릭 (Advanced Similarity Metrics)

사후 감사(`audit`) 시 사용되는 4가지 레이어의 기술적 작동 방식입니다.

### L1: Script Similarity (코드 유사도)
- **Alpha-Equivalence**: `DataFlowSimplifier`가 `var = expr; result = var`와 같은 중복 할당을 `result = expr`로 인라이닝하여 논리 구조를 일치시킵니다.
- **Levenshtein Distance (30%)**: 정규화된 코드 문자열 간의 편집 거리를 측정하여 구조적 유사성 파악.
- **Token Jaccard (70%)**: Python 토큰 단위로 분해하여 집합 유사도를 계산. 
- **가중치 부여 근거 (30:70)**: CAD 스크립트는 동일한 형상을 만들더라도 작성자(또는 AI)에 따라 연산의 순서나 구조가 쉽게 바뀝니다. 순서에 극도로 민감한 Levenshtein 거리의 비중을 30%로 낮춰 기본 구조만 점검하고, 순서가 바뀌어도 사용된 핵심 키워드와 파라미터(토큰) 교집합을 찾아내는 Jaccard의 비중을 70%로 높여 유연하고 강건한 유사도를 산출합니다.

### L2: B-rep Similarity (위상 유사도)
- **Topological Score**: 꼭짓점, 엣지, 면의 개수 차이를 가중 평균하여 비교.
- **Physical Score**: 부피(Volume)와 표면적(Area)의 상대적 오차 측정.
- **중요도**: 전체 유사도의 50% 가중치를 가지는 핵심 지표.

### L3: Mesh Similarity (형상 유사도)
- **Chamfer Distance (CD)**: 두 STL 메시의 표면에서 샘플링된 점 집합 $A, B$ 간의 평균 최근접 거리의 합을 계산.
  $$CD(A, B) = \frac{1}{|A|} \sum_{a \in A} \min_{b \in B} \|a-b\|^2 + \frac{1}{|B|} \sum_{b \in B} \min_{a \in A} \|a-b\|^2$$
- **특징**: Hausdorff 거리보다 이상치(Outlier)에 강건하며, 실제 형상의 기하학적 일치도를 정밀하게 측정.
- **결정성**: `build123d` 테셀레이션 파라미터(`tolerance=0.01`)를 고정하여 항상 동일한 메시 생성 보장.

### L4: Weighted Fusion (종합 유사도)
최종 점수는 각 레이어의 점수를 학술적으로 최적화된 가중치로 합산합니다.
- **공식**: `Score = (L1 * 0.2) + (L2 * 0.5) + (L3 * 0.3)`
- **가중치 분배 근거**:
    - **L2 B-rep (0.5)**: B-rep은 3D CAD 모델의 수학적 '정답(Ground Truth)'입니다. 근사치가 없는 완벽한 위상과 기하 정보를 담고 있으므로(GC-CAD 등 최신 논문에서도 핵심 피처로 사용), 기능적 동일성을 판단하는 가장 강력한 지표로서 50%를 부여합니다.
    - **L3 Mesh (0.3)**: 점 군(Point Cloud) 기반의 표면 근사치입니다. 직관적인 전체 형태의 유사성을 잘 잡아내므로 보조 기하 지표로서 30%를 부여합니다.
    - **L1 Script (0.2)**: CAD 스크립트 특성상, 완전히 동일한 원기둥을 만들더라도 "원을 그리고 돌출(Extrude)"하는 방식과 "사각형을 회전(Revolve)"하는 방식 등 코드가 완전히 다를 수 있습니다. 즉, 코드가 다르다고 해서 결과물이 다르다는 보장이 없기 때문에 오탐(False Negative)을 방지하고자 가장 낮은 20%의 가중치를 부여합니다.
- **판정 임계값**:

    - **DUPLICATE (≥ 0.85)**: 사실상 동일한 설계. 표절 또는 중복 등록.
    - **SIMILAR (0.60 ~ 0.85)**: 파라미터 수정 또는 파생 설계.
    - **DIFFERENT (< 0.60)**: 독창적인 신규 설계.

---

## 5. 조회 및 검증 메커니즘

프롬프트의 모호성을 극복하기 위해 다중 경로 역조회(Reverse Lookup)를 지원합니다.
- **Verify by Prompt**: 특정 프롬프트로 생성된 기록 조회.
- **Verify by Script**: 특정 코드 파일과 논리적으로 동일한 코드가 등록된 적이 있는지 조회.
- **Verify by Geometry**: 특정 STEP 파일과 형상적으로 동일한 모델이 등록된 적이 있는지 조회.

이 다층 구조를 통해 T2C-Prov는 AI 생성 CAD의 신뢰성을 기술적으로 완벽하게 보장합니다.
