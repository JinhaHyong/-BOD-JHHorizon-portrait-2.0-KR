# JHnode 3.0.1

검은사막 초상화 교체·텍스트 편집·게임 폰트 변경 프로그램입니다.
Windows 10 / 11 64비트에서 사용합니다. 배포 EXE는 Python 설치 없이 실행할 수 있습니다.

## 다운로드

- [단일 EXE](https://github.com/JinhaHyong/-BOD-JHHorizon-portrait-2.0-KR/releases/latest/download/JHnode.exe)
- [EXE·안내·라이선스 ZIP](https://github.com/JinhaHyong/-BOD-JHHorizon-portrait-2.0-KR/releases/latest/download/JHnode-Single-Windows-x64.zip)

## 사용 방법

1. 프로그램을 실행하고 현재 초상화 폴더와 새 초상화 폴더를 선택합니다.
2. 왼쪽에서 교체할 캐릭터, 오른쪽에서 새 초상화를 선택합니다.
3. 미리보기를 확인한 뒤 **초상화 교체**를 누릅니다.

기본 초상화 위치는 Windows 문서 폴더의 `Black Desert/FaceTexture`입니다.
실제 BMP 형식이며 가로 624·세로 804픽셀 이하인 이미지를 지원합니다.
이전 파일은 현재 초상화 폴더의 `backup` 폴더에 별도로 보관합니다.
프로그램에는 초상화 이미지가 포함되지 않습니다.

## 초상화 텍스트 편집

새 초상화를 고르면 미리보기 안에 편집 아이콘이 나타납니다.
별도 편집창에서 텍스트 박스를 만들고 마우스로 이동하거나 크기를 바꿀 수 있습니다.
박스를 더블클릭해 내용을 입력하고 글꼴·크기·색상·정렬·굵게·기울임·진하게·그림자,
박스 배경색과 불투명도를 조절합니다. 박스 안의 글자는 세로 중앙 정렬합니다.

사진별 편집 내용과 최근 설정을 저장하며, 같은 모양·위치의 설정은 중복 표시하지 않습니다.
여러 초상화에 설정을 적용할 때 박스 개수가 같으면 사진별 기존 내용을 유지합니다.
개수가 다르면 확인 후 현재 박스 설정으로 덮어쓰고 내용을 비웁니다.
편집 결과를 게임에 적용하려면 메인 화면에서 초상화 교체를 진행합니다.

## 폰트 변경과 폰트 찾기

메인 화면 하단 언어 선택 옆 **Aa** 아이콘으로 폰트 변경창을 엽니다.
PC에 있는 실제 TTF 파일을 미리 보고 선택한 뒤 **폰트 적용**을 누릅니다.
별도 파일은 **폰트 추가**로 불러옵니다. 게임에는 `prestringtable/font/pearl.ttf`로 복사하며,
기존 파일은 백업합니다. 검은사막 실행 파일로 설치 위치를 확인한 뒤 복사합니다.
위치를 찾지 못하면 설치 폴더나 게임 바로가기를 선택할 수 있습니다.

폰트 변경창과 텍스트 편집창의 **눈누 폰트 찾기 ↗**를 누르면 기본 브라우저에서
https://noonnu.cc/ 를 엽니다. 폰트 제작자의 이용 조건을 확인한 뒤 배포처에서 직접 받고,
프로그램의 폰트 추가로 불러오세요. 텍스트 편집은 TTF·OTF, 게임 변경은 실제 TTF를 지원합니다.
눈누에 소개된 모든 폰트가 게임 사용을 허용하는 것은 아닙니다.

3.0.1에서는 내부 온라인 목록·웹 미리보기·자동 다운로드 기능과 그 리소스를 제거했습니다.
클릭하지 않으면 폰트 사이트에 접속하지 않습니다.
사용자가 이전에 설치하거나 다운로드한 파일, 게임에 이미 적용한 폰트는 자동 삭제하지 않습니다.

## 테마·언어·설정

하단 해·달 아이콘으로 라이트·다크 모드를 바꾸고 한국어·영어를 선택합니다.
설정은 기존 호환 경로인 `%LOCALAPPDATA%/JHHorizon/PortraitManager`에 저장합니다.
EXE를 바꾸더라도 같은 사용자 계정의 설정을 유지합니다.
기존 기본 포함 폰트 경로를 참조하는 텍스트 설정은 나눔고딕 Bold로 불러옵니다.

## 라이선스

기본 포함 폰트와 소개 예시는 **나눔고딕 Bold** 원본을 사용합니다.
저작권은 NHN Corporation에 있으며 SIL Open Font License 1.1로 제공됩니다.
저작권·라이선스 원문은 `resources/font_licenses/NanumGothic-OFL.txt`와
`build_support/licenses/NanumGothic/OFL.txt`에 있습니다.
다른 직접 추가한 글꼴은 각 제작자의 게임 사용 등 이용 조건을 확인해야 합니다.

Python·PySide6/Qt·Pillow 등의 고지와 라이선스는 배포 ZIP의 `licenses` 및
`THIRD-PARTY-NOTICES.txt`에 포함됩니다. 프로그램 소스의 라이선스는 `LICENSE.md`를 확인하세요.

## 개발·빌드

Python 3.12 64비트에서 `requirements.txt`를 설치하고 `python main.py`로 실행합니다.
소스 구조는 `core`(설정·데이터), `services`(파일 처리), `ui`(화면)로 나뉩니다.
폰트 사이트 연결은 `ui/font_sources.py`, 기존 사용자 폰트 저장 경로는 `core/local_fonts.py`입니다.

테스트: `python -m unittest discover -s tests -v`
빌드 준비: `requirements-build.txt` 설치 후 `build_exe.ps1 -Mode single` 또는 `-Mode folder`.
빌드 시 `JHnode.spec`은 개인 설정·게임 이미지·사용자 다운로드 파일을 포함하지 않습니다.
`build_support/deployment_check.py`는 패키지 검증용 임시 환경에서만 파일 작업을 합니다.

배포 전 실제 단일 EXE를 Python이 없는 Windows 환경에서 검증합니다.
