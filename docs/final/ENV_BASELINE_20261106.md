# 合併前環境基準（2026-11-06）

合併 ODC_GMAT_DRL 進 `medal/` 之前兩邊的版本。合併後兩邊仍是**各自獨立的 uv 專案**（各自的 `uv.lock`、`.venv`），
這份清單是「合併後版本沒動」的對照依據：在合併後的目錄跑 `uv pip freeze`，應跟這裡逐行相同。

兩個 repo 都打了本機 tag `pre-monorepo-20261106`（沒有 push）。

| | 排位賽（ODC_Program，根目錄） | 金／銅牌賽（ODC_GMAT_DRL → `medal/`） |
|---|---|---|
| remote | `happpycorn/ODC_GMAT_Planner` | `git@github.com:happpycorn/ODC_GMAT_DRL.git` |
| branch | `Master` | `main` |
| HEAD | `52723c4b475fa001cbd446fde3ce9a4fc15a80d0` | `6fe29bc54c090d64514bb3ef3c786058e7248813` |
| Python | 3.12.12 | 3.12.12 |
| 主要套件 | numpy 1.26.0、numba 0.65.1、scipy 1.16.3、astropy 5.3.4、poliastro 0.17.0 | numpy 2.5.0、numba 0.67.0、scipy 1.18.1、torch 2.12.1、stable-baselines3 2.9.0 |
| uv | 0.9.21 | 0.9.21 |

## 排位賽 `uv pip freeze`

```
astropy==5.3.4
astroquery==0.4.11
beautifulsoup4==4.15.0
certifi==2026.6.17
charset-normalizer==3.4.7
contourpy==1.3.3
cycler==0.12.1
fonttools==4.63.0
html5lib==1.1
idna==3.18
jaraco-classes==3.4.0
jaraco-context==6.1.2
jaraco-functools==4.5.0
jplephem==2.24
keyring==25.7.0
kiwisolver==1.5.0
llvmlite==0.47.0
matplotlib==3.11.0
mealpy==3.0.3
more-itertools==11.1.0
numba==0.65.1
numpy==1.26.0
opfunu==1.0.4
packaging==26.2
pandas==3.0.3
pillow==12.2.0
plotly==5.24.1
poliastro==0.17.0
pyerfa==2.0.1.5
pyparsing==3.3.2
python-dateutil==2.9.0.post0
pyvo==1.9.1
pyyaml==6.0.3
requests==2.34.2
scipy==1.16.3
six==1.17.0
soupsieve==2.8.4
tenacity==9.1.4
threadpoolctl==3.7.0
tqdm==4.70.0
typing-extensions==4.15.0
urllib3==2.7.0
webencodings==0.5.1
```

## 金／銅牌賽 `uv pip freeze`

```
absl-py==2.4.0
ale-py==0.12.0
alembic==1.18.5
cloudpickle==3.1.2
colorlog==6.10.1
contourpy==1.3.3
cycler==0.12.1
farama-notifications==0.0.6
filelock==3.29.4
fonttools==4.63.0
fsspec==2026.6.0
grpcio==1.81.1
gymnasium==1.3.0
iniconfig==2.3.0
jinja2==3.1.6
kiwisolver==1.5.0
llvmlite==0.49.0
mako==1.3.12
markdown==3.10.2
markdown-it-py==4.2.0
markupsafe==3.0.3
matplotlib==3.11.0
mdurl==0.1.2
mpmath==1.3.0
networkx==3.6.1
numba==0.67.0
numpy==2.5.0
opencv-python==4.13.0.92
optuna==4.9.0
packaging==26.2
pandas==3.0.3
pillow==12.2.0
pluggy==1.6.0
protobuf==7.35.1
psutil==7.2.2
pygame-ce==2.5.7
pygments==2.20.0
pyparsing==3.3.2
pytest==9.1.1
python-dateutil==2.9.0.post0
pyyaml==6.0.3
rich==15.0.0
scipy==1.18.1
setuptools==81.0.0
six==1.17.0
sqlalchemy==2.0.51
stable-baselines3==2.9.0
sympy==1.14.0
tensorboard==2.20.0
tensorboard-data-server==0.7.2
torch==2.12.1
tqdm==4.68.3
typing-extensions==4.15.0
werkzeug==3.1.8
```
