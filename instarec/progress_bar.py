from datetime import datetime

from tqdm.asyncio import tqdm


class ProgressBar:
    def __init__(self, stream_name: str, total: int | None = None):
        self.stream_name = stream_name
        bar_format = (
            "{desc}: [{elapsed}<{remaining}, {rate_fmt}] {n_fmt}/{total_fmt} {bar} {percentage:3.0f}%"
            if total is not None
            else "{desc}: [{elapsed}, {rate_fmt}] {n_fmt} {bar}"
        )
        self._pbar = tqdm(total=total, unit="ts", bar_format=bar_format, dynamic_ncols=True)
        self._update_description()

    def _update_description(self):
        time_now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        desc = f"{time_now_str} - INFO - [{self.stream_name}]"
        self._pbar.set_description(desc, refresh=False)

    def update(self, amount: int):
        self._update_description()
        self._pbar.update(amount)

    def set_total(self, new_total: int):
        self._pbar.total = new_total
        self._pbar.refresh()

    def close(self):
        self._pbar.close()
