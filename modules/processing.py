# Patched classes to adapt from A111 webui for ComfyUI
from nodes import common_ksampler, VAEEncode, VAEDecode
from utils import pil_to_tensor, tensor_to_pil, get_mask_region, expand_crop_region, resize_image
import modules.shared as shared
import numpy as np
import torch
from PIL import Image, ImageFilter


class StableDiffusionProcessing:

    def __init__(self, init_img, model, positive, negative, vae, seed, steps, cfg, sampler_name, scheduler, denoise):
        # Variables used by the upscaler script
        self.init_images = [init_img]
        self.image_mask = None
        self.mask_blur = 0
        self.inpaint_full_res_padding = 0
        self.width = 0
        self.height = 0

        # ComfyUI Sampler inputs
        self.model = model
        self.positive = positive
        self.negative = negative
        self.vae = vae
        self.seed = seed
        self.steps = steps
        self.cfg = cfg
        self.sampler_name = sampler_name
        self.scheduler = scheduler
        self.denoise = denoise

        # Other required A1111 variables for the upscaler script that is currently unused in this script
        self.extra_generation_params = {}


class Processed:

    def __init__(self, p: StableDiffusionProcessing, images: list, seed: int, info: str):
        self.images = images
        self.seed = seed
        self.info = info

    def infotext(self, p: StableDiffusionProcessing, index):
        return None


def fix_seed(p: StableDiffusionProcessing):
    pass


def process_images(p: StableDiffusionProcessing) -> Processed:
    # Where the main image generation happens in A1111

    # Setup
    image_mask = p.image_mask.convert('L')
    init_image = p.init_images[0]

    # Blur the mask
    if p.mask_blur > 0:
        image_mask = image_mask.filter(ImageFilter.GaussianBlur(p.mask_blur))

    # Locate the white region of the mask outlining the tile and add padding
    crop_region = get_mask_region(image_mask, p.inpaint_full_res_padding)
    crop_region = expand_crop_region(crop_region, p.width, p.height, image_mask.width, image_mask.height)

    # Crop the init_image to get the tile that will be used for generation
    tile = init_image.crop(crop_region)
    initial_tile_size = tile.size
    tile = resize_image(tile, p.width, p.height)

    # Encode the image
    vae_encoder = VAEEncode()
    (latent,) = vae_encoder.encode(p.vae, pil_to_tensor(tile))

    # Generate samples
    (samples,) = common_ksampler(p.model, p.seed, p.steps, p.cfg, p.sampler_name,
                                 p.scheduler, p.positive, p.negative, latent, denoise=p.denoise)

    # Decode the sample
    vae_decoder = VAEDecode()
    (decoded,) = vae_decoder.decode(p.vae, samples)

    # Convert the sample to a PIL image
    tile_sampled = tensor_to_pil(decoded)

    # Resize back to the original size
    tile_sampled = resize_image(tile_sampled, initial_tile_size[0], initial_tile_size[1])

    # Put the tile into position
    image_tile_only = Image.new('RGB', init_image.size)
    image_tile_only.paste(tile_sampled, crop_region[:2])

    # Add the mask as an alpha channel
    image_tile_only.putalpha(image_mask)

    # Add back the tile to the initial image according to the mask in the alpha channel
    result = init_image.convert('RGBA')
    result.alpha_composite(image_tile_only)

    # Return the original image instead of the generated image because the masked parts of the image are noised
    processed = Processed(p, [result], p.seed, None)
    return processed
