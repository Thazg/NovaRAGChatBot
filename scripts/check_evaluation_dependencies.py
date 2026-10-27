"""Exercise optional neural retrieval APIs on tiny local models, without downloads.

This checks dependency compatibility and numerical output, not retrieval quality.
Install backend/requirements-evaluation.txt before running this script.
"""

from pathlib import Path
import tempfile


def main() -> None:
    import numpy as np
    import torch
    import transformers
    from sentence_transformers import CrossEncoder, SentenceTransformer
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import (
        BertConfig,
        BertForSequenceClassification,
        BertModel,
        PreTrainedTokenizerFast,
    )

    torch.set_num_threads(2)
    torch.manual_seed(0)
    vocabulary = {
        '[PAD]': 0, '[UNK]': 1, '[CLS]': 2, '[SEP]': 3,
        'document': 4, 'question': 5, 'answer': 6, 'evidence': 7,
    }
    raw_tokenizer = Tokenizer(WordLevel(vocabulary, unk_token='[UNK]'))
    raw_tokenizer.pre_tokenizer = Whitespace()
    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=raw_tokenizer,
        unk_token='[UNK]', pad_token='[PAD]', cls_token='[CLS]', sep_token='[SEP]',
        model_max_length=32,
    )
    config = BertConfig(
        vocab_size=len(vocabulary), hidden_size=16, num_hidden_layers=1,
        num_attention_heads=2, intermediate_size=32,
        max_position_embeddings=32, num_labels=1,
    )

    with tempfile.TemporaryDirectory(prefix='nova-evaluation-compat-') as directory:
        dense_path = Path(directory) / 'dense'
        reranker_path = Path(directory) / 'reranker'
        BertModel(config).save_pretrained(dense_path, safe_serialization=True)
        tokenizer.save_pretrained(dense_path)
        BertForSequenceClassification(config).save_pretrained(
            reranker_path, safe_serialization=True,
        )
        tokenizer.save_pretrained(reranker_path)

        dense = SentenceTransformer(
            str(dense_path), device='cpu', local_files_only=True,
            trust_remote_code=False,
        )
        vectors = dense.encode(
            ['document evidence', 'question answer'], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )
        if vectors.shape != (2, 16) or not np.isfinite(vectors).all():
            raise RuntimeError('Invalid local sentence-embedding output')
        if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5):
            raise RuntimeError('Sentence-embedding normalization failed')

        reranker = CrossEncoder(
            str(reranker_path), device='cpu', local_files_only=True,
            trust_remote_code=False,
        )
        scores = np.asarray(reranker.predict(
            [['question', 'document evidence'], ['question', 'answer']],
            show_progress_bar=False,
        ))
        if scores.size != 2 or not np.isfinite(scores).all():
            raise RuntimeError('Invalid local cross-encoder output')

    print(
        f'Optional evaluation compatibility passed: torch={torch.__version__}, '
        f'transformers={transformers.__version__}; tiny local CPU models only, '
        'no benchmark-quality measurement.'
    )


if __name__ == '__main__':
    main()
