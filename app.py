#!/usr/bin/env python
# encoding: utf-8
import gradio as gr
from PIL import Image
import traceback
import re
import torch
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model # type: ignore
import argparse
from transformers import AutoModel, AutoTokenizer

# Configuration for image classification model
class_names = ['Calculus', 'Dental Caries', 'Gingivitis', 'Hypodontia', 'Tooth Discoloration']
cnn_model = load_model('models/new_model2.h5')

# Argparser
parser = argparse.ArgumentParser(description='demo')
parser.add_argument('--device', type=str, default='cpu', help='cpu')
parser.add_argument('--dtype', type=str, default='fp32', help='fp32')
args = parser.parse_args()
device = args.device
assert device in ['cpu']

# Set dtype
if args.dtype == 'fp32':
    dtype = torch.float32
else:
    dtype = torch.float16

# Load model
model_path = 'openbmb/MiniCPM-V-2'
model = AutoModel.from_pretrained(model_path, trust_remote_code=True).to(dtype=dtype)
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

model = model.to(device=device)
model.eval()

ERROR_MSG = "Error, please retry"
model_name = 'MiniCPM-V 2.0'

# UI Components
form_radio = {
    'choices': ['Beam Search', 'Sampling'],
    'value': 'Sampling',
    'interactive': True,
    'label': 'Decode Type'
}

# Sliders and their settings
num_beams_slider = {'minimum': 0, 'maximum': 5, 'value': 3, 'step': 1, 'interactive': True, 'label': 'Num Beams'}
repetition_penalty_slider = {'minimum': 0, 'maximum': 3, 'value': 1.2, 'step': 0.01, 'interactive': True, 'label': 'Repetition Penalty'}
repetition_penalty_slider2 = {'minimum': 0, 'maximum': 3, 'value': 1.05, 'step': 0.01, 'interactive': True, 'label': 'Repetition Penalty'}
max_new_tokens_slider = {'minimum': 1, 'maximum': 4096, 'value': 1024, 'step': 1, 'interactive': True, 'label': 'Max New Tokens'}
top_p_slider = {'minimum': 0, 'maximum': 1, 'value': 0.8, 'step': 0.05, 'interactive': True, 'label': 'Top P'}
top_k_slider = {'minimum': 0, 'maximum': 200, 'value': 100, 'step': 1, 'interactive': True, 'label': 'Top K'}
temperature_slider = {'minimum': 0, 'maximum': 2, 'value': 0.7, 'step': 0.05, 'interactive': True, 'label': 'Temperature'}

def classify_images(image):
    # Check if the image is None
    if image is None:
        return "No image uploaded. Please upload a dental image."

    # Resize and preprocess the image
    try:
        input_image = tf.image.resize(image, (180, 180))  # Resize to expected input size
        input_image_array = tf.keras.utils.img_to_array(input_image)
        input_image_exp_dim = tf.expand_dims(input_image_array, axis=0)

        # Make predictions
        predictions = cnn_model.predict(input_image_exp_dim)
        result = tf.nn.softmax(predictions[0])
        
        # Prepare the outcome message
        outcome = f'The image belongs to {class_names[np.argmax(result)]} with a score of {np.max(result) * 100:.2f}%'
        return outcome
    except Exception as e:
        return f"Error processing the image: {str(e)}"
    
def create_component(params, comp='Slider'):
    if comp == 'Slider':
        return gr.Slider(**params)
    elif comp == 'Radio':
        return gr.Radio(choices=params['choices'], value=params['value'], interactive=params['interactive'], label=params['label'])
    elif comp == 'Button':
        return gr.Button(value=params['value'], interactive=True)

def chat(img, msgs, ctx, params=None):
    default_params = {"num_beams": 3, "repetition_penalty": 1.2, "max_new_tokens": 1024}
    if params is None:
        params = default_params
    if img is None:
        return -1, "Error, invalid image, please upload a new image", None, None
    try:
        image = img.convert('RGB')
        answer, context, _ = model.chat(image=image, msgs=msgs, context=None, tokenizer=tokenizer, **params)
        res = re.sub(r'(<box>.*</box>)', '', answer).replace('<ref>', '').replace('</ref>', '').replace('<box>', '').replace('</box>', '')
        return 0, res, None, None
    except Exception as err:
        print(err)
        traceback.print_exc()
        return -1, ERROR_MSG, None, None

def upload_img(image, _chatbot, _app_session):
    image = Image.fromarray(image)
    _app_session['sts'] = None
    _app_session['ctx'] = []
    _app_session['img'] = image
    _chatbot.append(('', 'Image uploaded successfully, you can talk to me now'))
    return _chatbot, _app_session

def respond(_question, _chat_bot, _app_cfg, params_form, num_beams, repetition_penalty, repetition_penalty_2, top_p, top_k, temperature):
    if _app_cfg.get('ctx', None) is None:
        _chat_bot.append((_question, 'Please upload an image to start'))
        return '', _chat_bot, _app_cfg

    _context = _app_cfg['ctx'].copy()
    _context.append({"role": "user", "content": _question})

    if params_form == 'Beam Search':
        params = {'sampling': False, 'num_beams': num_beams, 'repetition_penalty': repetition_penalty, "max_new_tokens": 896}
    else:  # Ensure this block is executed for Sampling
        params = {
            'sampling': True,
            'top_p': top_p,
            'top_k': top_k,
            'temperature': temperature,
            'repetition_penalty': repetition_penalty_2,
            "max_new_tokens": 896
        }
    
    code, _answer, _, sts = chat(_app_cfg['img'], _context, None, params)
    
    _context.append({"role": "assistant", "content": _answer}) 
    _chat_bot.append((_question, _answer))
    if code == 0:
        _app_cfg['ctx'] = _context
        _app_cfg['sts'] = sts
    return '', _chat_bot, _app_cfg

def clear(chat_bot, app_session):
    app_session['img'] = None
    chat_bot.clear()
    return chat_bot

with gr.Blocks() as demo:
    gr.Markdown("<h1 style='text-align: center;'>Medical Assistant</h1>")

    with gr.Tab("Image Classification"):
        with gr.Row():
            image_input = gr.Image(type='numpy', label="Upload Dental Image")
            classification_output = gr.Label(num_top_classes=5, label="Classification Results")
        image_input.change(fn=classify_images, inputs=image_input, outputs=classification_output)
    
    with gr.Tab("Medical Chatbot"):
        with gr.Row():
            with gr.Column(scale=2, min_width=300):
                app_session = gr.State({'sts': None, 'ctx': None, 'img': None})
                bt_pic = gr.Image(label="Upload an image to start")
                txt_message = gr.Textbox(label="Ask your question...")
            
            with gr.Column(scale=2, min_width=300):
                chat_bot = gr.Chatbot(label=f"Chatbot")
                clear_button = gr.Button(value='Clear')
                txt_message.submit(
                    respond, 
                    [txt_message, chat_bot, app_session], 
                    [txt_message, chat_bot, app_session]
                )

                bt_pic.upload(lambda: None, None, chat_bot, queue=False).then(upload_img, inputs=[bt_pic, chat_bot, app_session], outputs=[chat_bot, app_session])
                clear_button.click(clear, [chat_bot, app_session], chat_bot)

# Launch
demo.launch(share=True, debug=True, show_api=False)