"""
Модуль выявления опечаток, лексического и семантического подобия дисциплин.
Использует RapidFuzz (опечатки, перестановки) и FastEmbed ONNX (семантические эмбеддинги).
"""
import re
from typing import List, Dict, Set, Tuple, Optional
import numpy as np
from rapidfuzz import fuzz

from plan_analyzer.models import DisciplineSimilarityPair, DisciplineOccurrence


def clean_for_matching(text: str) -> str:
    """Нормализует название дисциплины для сопоставления."""
    t = text.lower().replace("ё", "е")
    # Удаление служебных скобок типа (1 семестр), (базовый уровень)
    t = re.sub(r"[\"'\(\)\[\],.;:!?\-—–]", " ", t)
    # Замена римских цифр на арабские (I -> 1, II -> 2, III -> 3, IV -> 4)
    t = re.sub(r"\biv\b", "4", t)
    t = re.sub(r"\biii\b", "3", t)
    t = re.sub(r"\bii\b", "2", t)
    t = re.sub(r"\bi\b", "1", t)
    return " ".join(t.split())


class DisciplineSimilarityEngine:
    """Движок анализа подобия дисциплин."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._embed_model = None

    def _get_model(self):
        """Ленивая инициализация модели FastEmbed."""
        if self._embed_model is None:
            try:
                from fastembed import TextEmbedding
                self._embed_model = TextEmbedding(model_name=self.model_name)
            except Exception as e:
                # В случае недоступности fastembed используем fallback
                self._embed_model = False
        return self._embed_model

    def compute_similarity_pairs(
        self,
        occurrences_by_discipline: Dict[str, List[DisciplineOccurrence]],
        min_score: float = 0.75,
        use_embeddings: bool = True,
    ) -> List[DisciplineSimilarityPair]:
        """
        Находит все пары схожих дисциплин с коэффициентом подобия >= min_score.
        Помечает скрытые коллизии (когда похожие дисциплины читаются разными кафедрами).
        """
        titles = list(occurrences_by_discipline.keys())
        n = len(titles)
        if n < 2:
            return []

        # 1. Извлекаем кафедры по каждой дисциплине
        depts_by_title: Dict[str, Set[str]] = {}
        for t, occs in occurrences_by_discipline.items():
            depts_by_title[t] = {occ.dept_name for occ in occs if occ.dept_name}

        # 2. Вычисление эмбеддингов
        embeddings = None
        if use_embeddings:
            model = self._get_model()
            if model:
                try:
                    raw_embeds = list(model.embed(titles))
                    embed_mat = np.array(raw_embeds)
                    # Нормализация векторов L2
                    norms = np.linalg.norm(embed_mat, axis=1, keepdims=True)
                    norms[norms == 0] = 1.0
                    embeddings = embed_mat / norms
                except Exception:
                    embeddings = None

        pairs: List[DisciplineSimilarityPair] = []

        # 3. Попарное сравнение
        for i in range(n):
            title_a = titles[i]
            clean_a = clean_for_matching(title_a)
            depts_a = depts_by_title.get(title_a, set())
            plans_count_a = len({occ.plan_file for occ in occurrences_by_discipline[title_a]})

            for j in range(i + 1, n):
                title_b = titles[j]
                clean_b = clean_for_matching(title_b)

                # Лексическое сравнение (RapidFuzz)
                ratio = fuzz.ratio(clean_a, clean_b) / 100.0
                token_sort = fuzz.token_sort_ratio(clean_a, clean_b) / 100.0
                token_set = fuzz.token_set_ratio(clean_a, clean_b) / 100.0
                lex_score = max(ratio, token_sort, token_set * 0.95)

                # Семантическое сравнение (эмбеддинги)
                sem_score = 0.0
                if embeddings is not None:
                    sem_score = float(np.dot(embeddings[i], embeddings[j]))
                    sem_score = max(0.0, min(1.0, sem_score))

                # Комбинированный скор
                if embeddings is not None:
                    # Если лексика очень близкая (опечатка/перестановка)
                    if lex_score >= 0.85:
                        comb_score = max(lex_score, sem_score)
                    else:
                        # Взвешенный учет семантики и лексики
                        comb_score = max(sem_score, (lex_score * 0.4 + sem_score * 0.6))
                else:
                    comb_score = lex_score

                if comb_score >= min_score:
                    depts_b = depts_by_title.get(title_b, set())
                    plans_count_b = len({occ.plan_file for occ in occurrences_by_discipline[title_b]})

                    # Скрытая коллизия: кафедры дисциплин не имеют общих пересечений
                    has_dept_overlap = bool(depts_a & depts_b)
                    is_hidden_conflict = not has_dept_overlap and bool(depts_a) and bool(depts_b)

                    pairs.append(
                        DisciplineSimilarityPair(
                            discipline_a=title_a,
                            discipline_b=title_b,
                            lexical_similarity=round(lex_score, 4),
                            semantic_similarity=round(sem_score, 4),
                            combined_score=round(comb_score, 4),
                            depts_a=sorted(list(depts_a)),
                            depts_b=sorted(list(depts_b)),
                            is_hidden_conflict=is_hidden_conflict,
                            plans_count_a=plans_count_a,
                            plans_count_b=plans_count_b,
                        )
                    )

        # Сортируем: сначала скрытые коллизии, затем по убыванию сходства
        pairs.sort(key=lambda p: (not p.is_hidden_conflict, -p.combined_score))
        return pairs
