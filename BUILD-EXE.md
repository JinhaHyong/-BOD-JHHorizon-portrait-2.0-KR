# JHnode EXE 빌드

Windows x64, Python 3.12 x64에서 빌드합니다. 배포받는 사람에게 Python 설치는 필요하지 않습니다.

```powershell
python -m venv .venv-build
.venv-build\Scripts\python -m pip install -r requirements-build.txt
.venv-build\Scripts\Activate.ps1
.\build_exe.ps1
```

단일 EXE는 같은 환경에서 다음 명령으로 빌드합니다.

```powershell
.\build_exe.ps1 -Mode single
```

단일형 결과는 `dist/JHnode.exe`이며 외부 `_internal` 폴더 없이 실행합니다. 설정·다운로드 폰트는 기존 사용자 저장 경로를 사용합니다. 새 초상화 기본 위치는 임시 압축 해제 폴더가 아닌 실행 파일 옆입니다. 실행 시 내부 구성요소를 임시 폴더에 풀기 때문에 폴더형보다 시작이 느릴 수 있습니다. 동봉 고지문과 라이선스 문서는 실행 파일과 함께 배포하세요.

결과는 `dist/JHnode/JHnode.exe`입니다. **JHnode 폴더 전체를 ZIP으로 배포**해야 합니다. `_internal` 폴더와 라이선스 파일을 함께 보관하세요. 기존 설정, 다운로드 폰트, 사용자 초상화는 빌드에 포함되지 않습니다.

기본 폴더형은 시작할 때 매번 모든 파일을 임시 폴더에 푸는 시간을 피하고, Qt 라이브러리와 고지문을 분리해 둡니다. 두 형식은 같은 소스와 동일한 의존성 구성을 사용합니다.

빌드는 PATH를 최소화하여 다른 개발 도구의 DLL이 섞이지 않게 합니다. Qt가 사용하는 Windows ICU는 운영체제에서 읽고, MSVC 런타임은 Qt 패키지의 버전으로 통일합니다. Windows용 TLS 플러그인도 포함합니다.

## EXE 자체 검사

```powershell
Start-Process -FilePath .\dist\JHnode\JHnode.exe -ArgumentList '--deployment-check', 'C:\Temp\jhnode-check.json' -Wait
```

경로에 공백이 있으면 인수를 따옴표로 감싸세요. JSON의 `success`가 `true`이고 종료 코드가 0이어야 통과입니다. 검사는 임시 설정·합성 이미지·가짜 게임 위치만 사용하며 실제 사용자 설정이나 게임 파일을 변경하지 않습니다. 일반 실행에서는 검사 코드가 실행되지 않습니다.

Windows Sandbox용 파일은 배포 준비 폴더의 `Sandbox`에 있습니다. Python이 없는 별도 Windows에서 검사한 결과와 실제 검은사막 실행 후 적용 여부는 각각 따로 확인해야 합니다.

현재 창 크기는 기존 830×910이며 작은 화면과 높은 화면 배율에 대한 반응형 개선은 이번 범위에서 제외되었습니다.
