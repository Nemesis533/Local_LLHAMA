from diffusers import BitsAndBytesConfig, SD3Transformer2DModel
from diffusers import StableDiffusion3Pipeline
from transformers import T5EncoderModel
from huggingface_hub import get_token
import torch
import os
from dotenv import load_dotenv

load_dotenv()
hf_token = os.environ.get("HF_TOKEN") or get_token()
if not hf_token:
    raise RuntimeError("No HuggingFace token found. Run `hf auth login` or set HF_TOKEN in .env.")

model_id = "stabilityai/stable-diffusion-3.5-large-turbo"
cache_dir = "/mnt/fast_storage/diffusers"

nf4_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16
)
model_nf4 = SD3Transformer2DModel.from_pretrained(
    model_id,
    subfolder="transformer",
    quantization_config=nf4_config,
    torch_dtype=torch.bfloat16,
    cache_dir=cache_dir,
    token=hf_token
)

t5_nf4 = T5EncoderModel.from_pretrained("diffusers/t5-nf4", torch_dtype=torch.bfloat16, cache_dir=cache_dir, token=hf_token)

pipeline = StableDiffusion3Pipeline.from_pretrained(
    model_id, 
    transformer=model_nf4,
    text_encoder_3=t5_nf4,
    torch_dtype=torch.bfloat16,
    cache_dir=cache_dir,
    token=hf_token
)
# Ensure all non-quantized components are bfloat16 before offloading
pipeline.vae = pipeline.vae.to(torch.bfloat16)
pipeline.text_encoder = pipeline.text_encoder.to(torch.bfloat16)
pipeline.text_encoder_2 = pipeline.text_encoder_2.to(torch.bfloat16)
pipeline.enable_model_cpu_offload()

prompt = "A whimsical and creative image depicting a hybrid creature that is a mix of a waffle and a hippopotamus, basking in a river of melted butter amidst a breakfast-themed landscape. It features the distinctive, bulky body shape of a hippo. However, instead of the usual grey skin, the creature's body resembles a golden-brown, crispy waffle fresh off the griddle. The skin is textured with the familiar grid pattern of a waffle, each square filled with a glistening sheen of syrup. The environment combines the natural habitat of a hippo with elements of a breakfast table setting, a river of warm, melted butter, with oversized utensils or plates peeking out from the lush, pancake-like foliage in the background, a towering pepper mill standing in for a tree.  As the sun rises in this fantastical world, it casts a warm, buttery glow over the scene. The creature, content in its butter river, lets out a yawn. Nearby, a flock of birds take flight"

image = pipeline(
    prompt=prompt,
    num_inference_steps=4,
    guidance_scale=0.0,
    max_sequence_length=512,
).images[0]
image.save("whimsical.png")
print("Saved image successfully with NF4 quantization and CPU offload!")
