"""執行期日誌的單一設定點（HAP-68）。

在這之前全專案用裸 print() 印東西，過程碎念、原理解釋、no-op 全混在同一條 stdout 上，
很囉唆。這裡把輸出收斂成一個 logging.Logger，配三分法：

  • 事件 (發生了什麼 + 數字)        → logger.info / warning / error，預設顯示
  • 過程細節 (逐項比對、每趟完整報告) → logger.debug，預設不印，加 -v 或去 log 檔看
  • no-op / 原理解釋                → 直接不印（解釋寫在程式碼註解，不是餵給終端機）

準則：一條 log 回答「發生了什麼 + 數字」，不回答「為什麼會這樣 / 這在理論上代表什麼」。
後者屬於註解與文件，要懂原理的人去讀碼，不是滾終端機。

用法：進入點（main.py 等）開頭呼叫一次 setup()；其餘模組直接 `from src.runlog import log`
然後 log.info(...)／log.debug(...)。import 時已裝好一個預設 INFO console handler，所以
即使某個進入點忘了 setup()，logger 照樣能印（不會掉進 logging 的 last-resort 只印 WARNING）。
"""
import sys
import logging

from tqdm import tqdm

log = logging.getLogger("odc")

# console handler 想印到哪（預設 stdout，維持改版前 print() 的行為，方便 `> file` 導出）。
_CONSOLE_STREAM = sys.stdout

# 模組全域：目前 console 是不是 -v（有些地方要據此決定要不要把細節餵給 scipy 之類）。
_VERBOSE = False


class _TqdmHandler(logging.Handler):
    """透過 tqdm.write() 印，這樣 log 行不會把正在跑的搜尋進度條戳爛。

    進度條活在 stderr、會原地覆寫；一般 print() 直接寫終端機會跟它搶游標。tqdm.write()
    會先把進度條清乾淨、印完再畫回來，是 tqdm 官方對付這件事的方式。沒有進度條在跑時
    它就是普通的一行輸出。
    """

    def emit(self, record):
        try:
            tqdm.write(self.format(record), file=_CONSOLE_STREAM)
        except Exception:
            self.handleError(record)


def is_verbose() -> bool:
    """目前 console 是不是開了 -v（DEBUG 全印）。"""
    return _VERBOSE


def setup(verbose: bool = False, quiet: bool = False, logfile: str | None = None) -> None:
    """設定 odc logger 的 handlers。可重複呼叫（會先清掉舊 handlers）。

    verbose (-v)：console 印到 DEBUG（每趟完整報告、逐項比對、VNB 向量都出來）。
    quiet   (-q)：console 只印 WARNING 以上（適合排程/批次）。
    logfile ：不為 None 時，完整 DEBUG 一律寫進這個檔（mode='w'，只留最新一次執行），
              終端機再怎麼精簡，事後都追得回細節。
    """
    global _VERBOSE
    _VERBOSE = bool(verbose)

    log.setLevel(logging.DEBUG)   # 底層全收，讓各 handler 自己決定門檻
    log.propagate = False         # 不要往 root 再噴一份
    for h in list(log.handlers):
        log.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    console = _TqdmHandler()
    console.setLevel(logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO))
    console.setFormatter(logging.Formatter("%(message)s"))   # 乾淨輸出，不要 "INFO:odc:" 前綴
    log.addHandler(console)

    if logfile:
        fh = logging.FileHandler(logfile, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s",
                                          datefmt="%H:%M:%S"))
        log.addHandler(fh)


# import 當下先裝一個預設 INFO console handler，讓忘了 setup() 的進入點也能正常印。
setup()
