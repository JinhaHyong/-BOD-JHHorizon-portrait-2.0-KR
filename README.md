# JHnode — 검은사막 초상화·폰트 교체 프로그램

JHHorizon Portrait Manager를 PySide6로 옮기고, 초상화 텍스트 편집과 게임 폰트 변경 기능을 추가한 **JHnode 3.0**입니다. 한국어와 영어를 지원합니다.

## 다운로드

**[최신 버전 다운로드](https://github.com/JinhaHyong/-BOD-JHHorizon-portrait-2.0-KR/releases/latest)**

- **[JHnode.exe](https://github.com/JinhaHyong/-BOD-JHHorizon-portrait-2.0-KR/releases/latest/download/JHnode.exe)**: 파일 하나로 실행하는 Windows 64비트 버전입니다. Python 설치나 외부 `_internal` 폴더가 필요하지 않습니다.
- **[배포용 ZIP](https://github.com/JinhaHyong/-BOD-JHHorizon-portrait-2.0-KR/releases/latest/download/JHnode-Single-Windows-x64.zip)**: 같은 EXE와 사용 안내·라이선스 문서를 담았습니다.

Windows 10 / Windows 11 64비트용입니다. 실행 시 내부 파일을 임시 폴더에 풀기 때문에 창이 열리기까지 잠시 걸릴 수 있습니다. 온라인 폰트 갱신과 다운로드에는 인터넷 연결이 필요합니다.

## 주요 기능

- 현재·새 초상화 목록과 미리보기, 한글 파일명 검색, 원본 자동 백업
- 여러 텍스트 박스의 이동·크기 조절·정렬과 글꼴·색상·배경 투명도·굵게·기울임·진하게·그림자 설정
- 사진별 편집 기억, 최근 설정 불러오기, 여러 초상화에 설정 일괄 적용
- 내 PC·온라인 폰트 미리보기·다운로드와 게임용 TTF 적용
- 검은사막 설치 폴더 또는 바탕화면 바로가기를 통한 적용 위치 선택
- 라이트·다크 모드, 한국어·영어 전환

## 사용 방법

1. `JHnode.exe`를 실행합니다.
2. 현재 초상화 폴더와 새 초상화 폴더를 선택합니다.
3. 양쪽에서 사진을 선택합니다. 새 초상화 미리보기 안의 편집 아이콘으로 텍스트를 편집할 수 있습니다.
4. **초상화 교체**를 누릅니다. 이전 초상화는 현재 초상화 폴더의 `Backup` 폴더에 보관됩니다.
5. 게임 폰트는 창 하단의 **Aa** 아이콘으로 변경합니다.

초상화 목록은 실제 BMP 형식이며 가로 624, 세로 804픽셀 이하인 이미지를 지원합니다. 규격을 초과하는 이미지를 임의로 축소해 저장하지 않습니다.

설정, 사진별 편집, 최근 설정, 다운로드 폰트는 사용자별로 저장합니다. 기존 데이터를 이어 쓰기 위해 저장 경로는 `%LOCALAPPDATA%\JHHorizon\PortraitManager`를 유지합니다.

## 소스 실행과 빌드

현재 버전의 진입점은 **`main.py`**입니다. 과거 PyQt5 버전인 `JHHorizon portrait 2.0.py`는 기존 코드 보관용으로 남겼습니다.

Python 3.12 x64 환경에서:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

단일 EXE·폴더형 EXE 빌드는 **[BUILD-EXE.md](BUILD-EXE.md)**, 자세한 구현·사용 설명은 [개발 문서](docs/DEVELOPMENT.md)를 참고하세요.

| 경로 | 역할 |
| --- | --- |
| `main.py` | 앱 시작 |
| `core/` | 설정, 경로, 텍스트·폰트 데이터 |
| `services/` | 이미지 로딩, 백업·교체, 폰트 다운로드·적용 |
| `ui/` | PySide6 화면과 편집 도구 |
| `resources/` | 번역, 아이콘, 기본 글꼴, 폰트 미리보기 |
| `tests/` | 임시 데이터를 사용하는 기능 검사 |

## 검증

소스 테스트 **82개**를 통과했습니다. Python이 없는 Windows Sandbox에 **단일 EXE만 복사**해 두 차례 검사했으며, 각 실행의 **8개 배포 검사**와 일반 화면 실행을 확인했습니다. 임시 초상화·설정·가짜 게임 경로를 사용했고 실제 게임 파일은 검사에서 변경하지 않았습니다.

실제 게임 클라이언트를 실행한 뒤의 반영 여부는 사용 환경에서 확인해야 합니다. 현재 기본 창 크기는 830×910입니다.

## 라이선스와 제작자

Copyright (c) 2024 김진하 (Jinha Kim / JinhaHyong)

기존 [CC BY-NC 4.0 라이선스](LICENSE.md)를 유지합니다. 라이브러리와 폰트에는 각 구성요소의 라이선스가 적용됩니다. [구성요소 고지문](build_support/THIRD-PARTY-NOTICES.txt)을 참고하고 재배포할 때는 안내·라이선스 문서를 함께 보관하세요.

## English

JHnode 3.0 is the PySide6 successor to JHHorizon Portrait Manager. It adds draggable portrait text layers, reusable settings, batch styling, local and online font selection, game font replacement, and light/dark themes. Download the standalone Windows x64 executable from [Releases](https://github.com/JinhaHyong/-BOD-JHHorizon-portrait-2.0-KR/releases/latest). No separate Python installation is required. The current source entry point is `main.py`; the original 2.0 script is retained for reference.
