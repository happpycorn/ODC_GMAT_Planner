"""批次評測；在子模組匯入 numpy 前固定每個行程的 BLAS 執行緒。"""
from runtime_threads import limit_blas_threads

limit_blas_threads()
