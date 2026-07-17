# NOVA ModelScope Studio

This private Gradio Studio is the preflight endpoint for NOVA's digital-human
worker. It verifies the GPU and persistent disk before any large model weights
are downloaded.

The production inference package remains in the parent `deploy/modelscope`
directory and is enabled only after a free GPU allocation passes this check.
