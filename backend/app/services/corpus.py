"""对比语料库：内存倒排索引 + 句子级相似检索。

参考开源 paper_checking_system（tianlian0）的比对思想——连续公共串超过
阈值即判重——用 n-gram shingle 倒排索引召回候选句，再做精确 containment
比对。文档量在万级以内时内存索引足够快。

启动加速：索引与指纹可持久化到 `data/index.snapshot.pkl`（pickle v5，本机
可信数据目录内使用）。启动时若快照哈希与当前语料一致则直接加载，
否则全量重建并落盘；增量入库仅标记脏位，进程退出时统一回写。
"""
import atexit
import hashlib
import os
import pickle
import threading
from dataclasses import dataclass

from .. import config, db
from . import segmenter

SNAPSHOT_VERSION = 3  # 快照结构版本：结构变更时递增使旧快照失效
_dirty = {"flag": False}
_atexit_registered = {"done": False}


@dataclass
class Candidate:
    doc_id: int
    doc_title: str
    sent_idx: int
    sent_text: str
    sim: float


@dataclass
class CorpusDoc:
    doc_id: int
    title: str
    is_builtin: bool
    sentences: list[segmenter.Sentence]


def _snapshot_path() -> str:
    return str(config.DATA_DIR / "index.snapshot.pkl")


def _lm_state():
    from . import ngram_lm
    return ngram_lm.LM.state()


class Corpus:
    def __init__(self, snapshot_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self.docs: dict[int, CorpusDoc] = {}
        self.fingerprints: dict[int, int] = {}
        self.inverted: dict[str, list[tuple[int, int]]] = {}
        self.state_hash: str = ""
        self._dirty = False
        self._snap = snapshot_path or _snapshot_path()

    # ---------- 构建 ----------

    def _state_hash(self) -> str:
        """语料状态指纹：任一文档增删改都会变化，用于快照有效性校验。"""
        rows = db.all_docs_full()
        h = hashlib.sha256()
        h.update(f"v{SNAPSHOT_VERSION};n={len(rows)};".encode())
        for r in sorted(rows, key=lambda x: x["id"]):
            h.update(f"{r['id']}\x00{r['title']}\x00{len(r['content'])}\x1e".encode())
        return h.hexdigest()

    def rebuild(self) -> None:
        with self._lock:
            self.docs.clear()
            self.inverted.clear()
            self.fingerprints.clear()
            from .fingerprint import simhash
            for row in db.all_docs_full():
                did = int(row["id"])
                kind = segmenter.detect_language(row["content"])
                sents = [
                    s for s in segmenter.split_sentences(row["content"])
                    if s.units >= 4
                ]
                self.docs[did] = CorpusDoc(did, row["title"], bool(row["is_builtin"]), sents)
                self.fingerprints[did] = simhash(
                    segmenter.normalize(row["content"], kind), kind)
                for idx, s in enumerate(sents):
                    for sh in segmenter.shingles(s):
                        self.inverted.setdefault(sh, []).append((did, idx))
            self.state_hash = self._state_hash()

    def load_or_rebuild(self) -> str:
        """启动入口：快照哈希匹配则加载（亚秒级），否则全量重建并落盘。"""
        if not _atexit_registered["done"]:
            atexit.register(self.save_snapshot_if_dirty)
            _atexit_registered["done"] = True
        if os.path.exists(self._snap):
            with open(self._snap, "rb") as f:
                payload = pickle.load(f)
            if payload.get("v") == SNAPSHOT_VERSION and payload.get("hash") == self._state_hash():
                with self._lock:
                    docs_raw = payload["docs"]
                    self.docs = {
                        int(did): CorpusDoc(int(did), t, bool(b), s)
                        for did, (t, b, s) in docs_raw.items()
                    }
                    self.fingerprints = {int(k): v for k, v in payload["fp"].items()}
                    self.inverted = payload["inv"]
                    self.state_hash = payload["hash"]
                from . import ngram_lm
                ngram_lm.LM.set_state(payload.get("lm"))
                return "loaded"
        self.rebuild()
        self.save_snapshot()
        return "rebuilt"

    def save_snapshot(self) -> None:
        """原子写入快照（含 n-gram LM 状态，若已训练）。"""
        with self._lock:
            payload = {
                "v": SNAPSHOT_VERSION,
                "hash": self.state_hash,
                "docs": {did: (d.title, d.is_builtin, d.sentences) for did, d in self.docs.items()},
                "inv": self.inverted,
                "fp": self.fingerprints,
                "lm": _lm_state(),
            }
        tmp = self._snap + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, self._snap)
        self._dirty = False

    def save_snapshot_if_dirty(self) -> None:
        if self._dirty and self.state_hash:
            try:
                self.save_snapshot()
            except Exception:  # noqa: BLE001 — 退出时落盘失败不影响主流程
                pass

    def _mark_dirty(self) -> None:
        self._dirty = True

    # ---------- 增量 ----------

    def add_and_index(self, doc_id: int) -> None:
        """新文档入索引（增量）。"""
        row = db.get_doc_full(doc_id)
        if row is None:
            return
        with self._lock:
            did = int(row["id"])
            if did in self.docs:
                return
            kind = segmenter.detect_language(row["content"])
            sents = [
                s for s in segmenter.split_sentences(row["content"])
                if s.units >= 4
            ]
            self.docs[did] = CorpusDoc(did, row["title"], bool(row["is_builtin"]), sents)
            from .fingerprint import simhash
            self.fingerprints[did] = simhash(segmenter.normalize(row["content"], kind), kind)
            for idx, s in enumerate(sents):
                for sh in segmenter.shingles(s):
                    self.inverted.setdefault(sh, []).append((did, idx))
            self.state_hash = self._state_hash()   # 语料已变，重算状态指纹
            self._mark_dirty()

    def remove_doc(self, doc_id: int) -> None:
        with self._lock:
            self.docs.pop(doc_id, None)
            self.fingerprints.pop(doc_id, None)
            for key in list(self.inverted):
                self.inverted[key] = [p for p in self.inverted[key] if p[0] != doc_id]
                if not self.inverted[key]:
                    del self.inverted[key]
            self.state_hash = self._state_hash()   # 语料已变，重算状态指纹
            self._mark_dirty()

    def find_similar(self, sent: segmenter.Sentence, threshold: float, top: int = 3) -> list[Candidate]:
        """返回相似度 >= threshold 的候选句，按相似度降序。"""
        sh = segmenter.shingles(sent)
        if not sh:
            return []
        with self._lock:
            # 召回：shingle 命中次数排序
            hits: dict[tuple[int, int], int] = {}
            for s in sh:
                for pos in self.inverted.get(s, ()):  # (doc_id, sent_idx)
                    hits[pos] = hits.get(pos, 0) + 1
            if not hits:
                return []
            ranked = sorted(hits.items(), key=lambda kv: -kv[1])[:200]
            results: list[Candidate] = []
            seen = set()
            for (did, idx), _ in ranked:
                if did in seen:
                    continue
                doc = self.docs.get(did)
                if doc is None:
                    continue
                cand = doc.sentences[idx]
                sim = segmenter.similarity(sh, segmenter.shingles(cand))
                if sim >= threshold:
                    seen.add(did)
                    results.append(Candidate(did, doc.title, idx, cand.text, round(sim, 4)))
                if len(results) >= top:
                    break
            results.sort(key=lambda c: -c.sim)
            return results[:top]

    def stats(self) -> dict:
        with self._lock:
            chars = sum(
                sum(s.units for s in d.sentences) for d in self.docs.values()
            )
            builtin = sum(1 for d in self.docs.values() if d.is_builtin)
            return {
                "documents": len(self.docs),
                "builtin_documents": builtin,
                "sentences": sum(len(d.sentences) for d in self.docs.values()),
                "units": chars,
            }


CORPUS = Corpus()
