# Translation model notice

The optional background French translation runtime uses:

- Model: `Helsinki-NLP/opus-mt-tc-big-en-fr`
- Upstream: OPUS-MT / Helsinki-NLP
- Model page: https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-fr
- License declared by the model publisher: CC BY 4.0

The model weights are not committed to this repository. The VPS installer downloads
the upstream model temporarily, converts it to CTranslate2 INT8 for local inference,
keeps only the runtime model/tokenizer assets, and deletes the temporary source
weights and Hugging Face cache.

This notice is retained alongside the deployment code so the model attribution
remains visible even though the weights live only on the VPS.
