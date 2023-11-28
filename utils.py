import openai
from openai import OpenAI
from tavily import TavilyClient
import os
import ast
import torch
from diffusers import DiffusionPipeline, LCMScheduler
import requests
import io
from PIL import Image
import torch
import json


openai.api_key = os.getenv("OPENAI_API_KEY")
auth_token = os.getenv('HUGGINGFACE_API_KEY')
SDXL_API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

def generate_slide_titles(topic):
    client = OpenAI()
    title_suggestion_prompt = """Generate 10 compelling slide titles for a PowerPoint Presentation on the given topic. Format the output in JSON, with each key representing the slide number and its corresponding value being the slide title. Be creative and ensure that the titles cover key aspects of the topic, providing a comprehensive overview.

Topic = {topic}
"""
    completion = client.chat.completions.create(
        model = 'gpt-3.5-turbo-1106',
        messages=[
            {
                'role':'user',
                'content': title_suggestion_prompt.format(topic=topic)
            }
        ],
        response_format = {'type':'json_object'},
        seed = 42,
    )

    output = ast.literal_eval(completion.choices[0].message.content)
    return output

def generate_point_info(topic, n_points=5):
    client = OpenAI()
    info_gen_prompt = """You will be given a topic and your task is to generate {n_points} points of information on it. The points should be precise and plain sentences. Format the output as a JSON dictionary, where the key is the topic name and the value is a list of points.

Topic : {topic}
"""
    completion = client.chat.completions.create(
        model = 'gpt-3.5-turbo-1106',
        messages=[
            {
                'role':'user',
                'content': info_gen_prompt.format(topic=topic, n_points=n_points)
            }
        ],
        response_format = {'type':'json_object'},
        seed = 42,
    )

    output = ast.literal_eval(completion.choices[0].message.content)

    return output

def chat_generate_point_info(topic, n_points=5):
    client = OpenAI()
    info_gen_prompt = """You will be given a topic and your task is to generate {n_points} points of information on it. The points should be precise and plain sentences. Format the output as a JSON dictionary, where the key is the topic name and the value is a list of points.

Topic : {topic}
"""
    completion = client.chat.completions.create(
        model = 'gpt-3.5-turbo-1106',
        messages=[
            {
                'role':'user',
                'content': info_gen_prompt.format(topic=topic, n_points=n_points)
            }
        ],
        response_format = {'type':'json_object'},
        seed = 42,
    )

    output = ast.literal_eval(completion.choices[0].message.content)

    return output

def fetch_images_from_web(topic):
    tavily_client = TavilyClient(api_key=os.getenv('TAVILY_API_KEY'))
    search_results = tavily_client.search(topic, search_depth="advanced",include_images=True)
    images = search_results['images']
    return images

device_type = 'cuda' if torch.cuda.is_available() else 'cpu'

if device_type=='cuda':
    image_gen_model = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        variant="fp16",
        torch_dtype=torch.float16,
        use_auth_token = auth_token
    ).to("cuda")
    # SET SCHEDULER
    image_gen_model.scheduler = LCMScheduler.from_config(image_gen_model.scheduler.config)
    # LOAD LCM-LoRA
    image_gen_model.load_lora_weights("latent-consistency/lcm-lora-sdxl")

def generate_image(prompt):
    image_path = prompt + '.png'
    print('GENERATING IMAGE ON DEVICE TYPE:',device_type)
    if device_type == 'cuda':
        generator = torch.manual_seed(42)
        image = image_gen_model(
            prompt=prompt, num_inference_steps=4, generator=generator, guidance_scale=1.0
        ).images[0]

        image.save(image_path)
    
    else:
        headers = {"Authorization": "Bearer "+ auth_token}
        payload = {'inputs': prompt}
        response = requests.post(SDXL_API_URL, headers=headers, json = payload)
        print(response)
        image_bytes = response.content
        print(image_bytes[:100])
        image = Image.open(io.BytesIO(image_bytes)) 
        image.save(image_path)

    return image_path

def get_context():

    return 1



def create_vectordb():

    return 1

def generate_slide_titles_from_document(topic, context):
    client = OpenAI()
    info_gen_prompt = """Generate 5 most relvant and compelling slide titles for a PowerPoint Presentation on the given topic and based on the given context. \
    It should cover the major aspects of the context \
    Format the output in JSON, with each key representing the slide number and its corresponding value being the slide title. \
    Be creative and ensure that the titles cover key aspects of the topic, providing a comprehensive overview.

    Topic = {topic}

    Context = {context}
    """
    completion = client.chat.completions.create(
        model = 'gpt-3.5-turbo-1106',
        messages=[
            {
                'role':'user',
                'content': info_gen_prompt.format(topic= topic, context = context)
            }
        ],
        response_format = {'type':'json_object'},
        seed = 42,

    )

    output = ast.literal_eval(completion.choices[0].message.content)

    return output


