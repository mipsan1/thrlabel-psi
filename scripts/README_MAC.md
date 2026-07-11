# Mac(M3, Apple Silicon)에서 직접 실행하는 방법

이 문서는 **원격 인증 없이** 사용자가 자신의 Mac 터미널에서 직접 실행하는
절차입니다. 스크립트는 기본적으로 **읽기/빌드 작업만** 수행하며,
`sudo`를 절대 사용하지 않고, 시스템 패키지를 자동으로 설치하지 않습니다.

> **정직성 고지.** 이 저장소에는 실제 암호 구현(OPRF/OKVS/비밀분산)이 없습니다.
> 따라서 Python 실험이 내는 값은 모두 **시뮬레이션** 또는 **해석적(analytical)**
> 결과이며, **암호 wall-clock 측정치가 아닙니다.** 아래 feasibility 스크립트가
> upstream 암호 스택을 빌드하는 데 성공하더라도 그것은 "빌드/실행이 된다"는
> 사실일 뿐 **보안이 증명된 것은 아닙니다.**

---

## 0. 사전 준비 (한 번만)

터미널을 열고 이 저장소 폴더로 이동한 뒤, Python 의존성을 설치합니다.

```bash
cd <이-저장소-경로>
python3 -m venv .venv && source .venv/bin/activate      # 선택(권장)
python3 -m pip install -r requirements-dev.txt          # numpy, matplotlib, pytest
```

암호 스택 빌드에 필요한 시스템 도구(Xcode Command Line Tools, CMake, Ninja 등)가
없다면, 아래 1단계가 무엇이 빠졌는지 알려줍니다. 자동 설치는 하지 않으므로,
직접 설치하거나 `--install-deps` 옵션을 **명시적으로** 주어야 합니다.

---

## 1. 실행할 정확한 명령 (순서대로 3~5개)

### ① Python 시뮬레이션 · 테스트 · 그림 재생성 (가장 먼저, 가장 안전)

```bash
bash scripts/run_local_experiments.sh
```

- 산출물: `outputs/local_run_<타임스탬프>/`
  - `experiment_artifacts/` : `sim_results.json`, `thrlabel_tables.json`,
    `rq3_*.csv`, `rq4_*.csv`, `rq1_efficiency.csv`, `*.png`
  - `logs/` : 각 단계 로그
  - `local_experiments_summary.md` : 단계별 PASS/FAIL 요약
  - 같은 이름의 `.tar.gz` 아카이브
- 소요: 보통 1~2분.

### ② Mac 암호 스택 feasibility 점검 (읽기/빌드만, 설치 없음)

```bash
bash scripts/macos_feasibility.sh
```

- 먼저 **시스템/툴체인 상태만** 기록하고, 격리된 임시 디렉터리에서
  upstream `volePSI`(내부적으로 `libOTe`를 가져옴)를 clone → configure → build
  시도합니다. ARM64(`-DCMAKE_OSX_ARCHITECTURES=arm64`) 설정을 적용합니다.
- 빌드가 성공하면 upstream 유닛 테스트와 작은 PSI 예제를 실행합니다.
- 산출물: `outputs/mac_feasibility_<타임스탬프>/`
  - `system.txt` : OS/CPU/메모리 및 컴파일러·cmake·ninja·python 버전
  - `logs/` : clone/build/test 로그, upstream README 사본
  - `summary.json`, `summary.md` : 단계별 **PASS / FAIL / SKIP**
  - 같은 이름의 `.tar.gz`
- 만약 툴체인이 부족하다고 나오면 아래 ③으로 진행하세요.

### ③ (툴체인이 부족할 때만) Homebrew 의존성 설치 후 재시도

`--install-deps`를 **직접 명시**해야만 Homebrew 패키지를 설치합니다(sudo 없음).

```bash
bash scripts/macos_feasibility.sh --install-deps
```

- 설치 대상: `cmake ninja libsodium boost` (Homebrew, 사용자 권한).
- 설치 후 위 ②와 동일한 clone/build/test를 이어서 수행합니다.

### ④ (선택) 시뮬레이션 결과를 feasibility 폴더에 합쳐 수집

②가 만든 결과 폴더에 Python 산출물을 함께 모으고 싶다면:

```bash
bash scripts/run_local_experiments.sh --result-dir outputs/mac_feasibility_<타임스탬프>
```

### ⑤ (선택, 매우 느림) MP-SPDZ까지 빌드

```bash
bash scripts/macos_feasibility.sh --with-mpspdz
```

- MP-SPDZ를 clone/build만 합니다. **보안 비교(secure comparison)를 실행·검증하지는
  않습니다.** 기본값은 SKIP입니다.

---

## 2. 예상 산출물 요약

| 위치 | 내용 |
|------|------|
| `outputs/local_run_<ts>/experiment_artifacts/` | 표(JSON/CSV) + 그림(PNG) |
| `outputs/local_run_<ts>/local_experiments_summary.md` | Python 단계 PASS/FAIL |
| `outputs/mac_feasibility_<ts>/system.txt` | 시스템·툴체인 상태 |
| `outputs/mac_feasibility_<ts>/summary.md` `summary.json` | 빌드 단계 PASS/FAIL/SKIP |
| `outputs/*.tar.gz` | 위 폴더의 압축본(전달용) |

각 표/그림 산출물에는 `scenario`(예: `fraudring_t4`, `coverage_t3`)와
`provenance`(`simulation` / `analytical`)가 메타데이터로 기록됩니다.

---

## 3. 중단 / 재개

- **중단:** 실행 중 `Ctrl + C`로 언제든 안전하게 멈출 수 있습니다.
  이미 만들어진 로그·산출물은 그대로 보존됩니다(파괴적 정리 없음).
- **재개:** 스크립트는 실행할 때마다 **새 타임스탬프 폴더**를 만들므로, 그냥 다시
  같은 명령을 실행하면 됩니다. 이전 결과는 덮어쓰지 않습니다.
- **빌드가 너무 오래 걸릴 때:** `--build-timeout <초>` 로 각 빌드 단계에 상한을 둘 수
  있습니다(기본 3600초). 예: `bash scripts/macos_feasibility.sh --build-timeout 1200`.
- **임시 작업 디렉터리:** clone/build는 `mktemp -d`로 만든 격리된 임시 폴더에서만
  이뤄집니다. 스크립트는 이 폴더를 자동 삭제하지 않고 경로를 안내하니, 확인 후
  직접 `rm -rf`로 지우면 됩니다.

---

## 4. 안전 주의사항

- 이 스크립트들은 **`sudo`를 사용하지 않으며**, 시스템을 변경하는 파괴적 명령을
  실행하지 않습니다.
- `--install-deps` 없이는 어떤 시스템 패키지도 설치하지 않습니다.
- 외부 저장소 clone/build는 **격리된 임시 디렉터리 안에서만** 수행됩니다.
- `summary`/`system.txt`에는 도구 **버전만** 기록하며, 전체 환경변수·비밀·개인 파일
  트리를 수집하지 않습니다.
- `additive_share_demo`는 **보안 계산이 아닙니다**: 단일 프로세스 평문 공유이고,
  네트워크 MPC가 아니며, **구성(composition)·시뮬레이션 보안 증명이 없습니다.**
  이 데모의 목적은 산술이 성립하는지 확인하는 것뿐입니다.
- 로그에 보이는 어떤 시간(초) 값도 논문 측정치로 사용하지 마세요. 실제 측정에는
  완성된 암호 프로토타입이 필요합니다.

---

## 5. 결과를 전달할 때

`outputs/` 아래의 `*.tar.gz` 파일 하나만 공유하면, 시스템 상태 · 빌드 로그 ·
단계별 판정 · 시뮬레이션 산출물이 모두 담겨 있습니다.
