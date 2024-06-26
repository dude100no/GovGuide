# Standard
from dotenv import load_dotenv
import os
import json
from pydantic import BaseModel
from typing import List, Optional
import random
from datetime import datetime, timedelta
import requests
from urllib.parse import quote
import aiohttp
import asyncio
from uuid import uuid4

import os

# os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

# Cloudinary
import cloudinary
import cloudinary.uploader
import cloudinary.api

# ElevenLabs
from elevenlabs.client import ElevenLabs

# FastAPI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Whisper
import whisper_timestamped as whisper

# Movie Editing
import srt
import re
import difflib
from moviepy import editor
from PIL import Image
import numpy as np

from llm_server import ScriptGenerator, UserData

load_dotenv()

# Setup
app = FastAPI()
config = cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# CORS
origins = [
    "http://gov-guide.vercel.app",
    "https://gov-guide.vercel.app",
    "http://localhost",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HUGGINGFACE
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_CLIENT = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# PEXELS
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")


def generate_uuid():
    # Generate a random UUID
    uuid = "{:08x}-{:04x}-{:04x}-{:04x}-{:012x}".format(
        random.getrandbits(32),
        random.getrandbits(16),
        (random.getrandbits(12) & 0x0FFF) | 0x4000,
        (random.getrandbits(12) & 0x3FFF) | 0x8000,
        random.getrandbits(48),
    )
    return uuid


@app.get("/")
def index():
    return {"Hello": "World"}


def uploadFile(file: bytes, file_name: str, folder: str = "", file_type: str = 'auto') -> str:
    '''
    Use Cloudinary Upload to upload
    '''
    if "." in file_name:
        file_name = file_name.split(".")[0]
    file_upload = cloudinary.uploader.upload(
        file, public_id=file_name, unique_filename=False, overwrite=True, folder=folder, resource_type=file_type
    )
    srcURL = file_upload['url']
    return srcURL


@app.post("/")
def upload():
    srcURL = uploadFile(
        "https://cloudinary-devs.github.io/cld-docs-assets/assets/images/butterfly.jpeg", 'quickstart_butterfly'
    )
    return {"image": srcURL}


@app.post("/generateScript")
async def generateScript(UserData: UserData):
    script_gen = ScriptGenerator()
    script_json, sources = script_gen(UserData)
    
    script_json['sources'] = sources

    return script_json


class VoiceBody(BaseModel):
    subtitles: List[str]


@app.post("/generateVoice")
async def generateVoice(VoiceBody: VoiceBody):
    allText = "\n".join(VoiceBody.subtitles)
    voiceList = ELEVENLABS_CLIENT.voices.get_all().voices
    selectedVoice = random.choices(voiceList)
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    audio = ELEVENLABS_CLIENT.generate(text=allText, voice=selectedVoice[0])
    blob_name = f"audio_{current_time}_{generate_uuid()}.mp3"

    srcURL = uploadFile(b''.join(audio), blob_name, folder='audio', file_type="raw")

    # SRT File
    whisper_audio = whisper.load_audio(srcURL)
    model = whisper.load_model("base")

    result = whisper.transcribe(model, whisper_audio, language="en")

    srt_file = ""

    for i, segment in enumerate(result["segments"]):
        start, end = segment["start"], segment["end"]
        srt_file += f"{i + 1}\n00:00:{str(int(start)).replace('.', ',')} --> 00:00:{str(int(end)).replace('.', ',')}\n{segment['text'].strip()}\n"
    srt_blob_name = f"subtitles_{current_time}_{generate_uuid()}.srt"
    with open(srt_blob_name, 'w') as f:
        f.write(srt_file)
        f.close()
    with open(srt_blob_name, 'rb') as f:
        data = f.read()
        srt_srcURL = uploadFile(data, srt_blob_name, folder='srt', file_type="raw")
        f.close()
    os.remove(srt_blob_name)
    return {"audio": srcURL, "srt_file": srt_srcURL}


@app.post("/generateMusic")
async def generateMusic():
    music_style = ["slow pace loopable advertisement music"]
    random_music = music_style[random.randint(0, len(music_style) - 1)]
    API_URL = "https://api-inference.huggingface.co/models/facebook/musicgen-small"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}

    def query(payload):
        response = requests.post(API_URL, headers=headers, json=payload)
        return response.content

    audio_bytes = query(
        {
            "inputs": random_music,
        }
    )
    print(audio_bytes)
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    blob_name = f"music_{current_time}_{generate_uuid()}.mp3"
    srcURL = uploadFile(audio_bytes, blob_name, folder='music', file_type="raw")

    return {"music": srcURL}


class VideoBody(BaseModel):
    scene: List[str]


async def fetch_video(session, scene):
    url = f"https://api.pexels.com/videos/search?query={quote(scene)}&per_page=1&orientation=landscape&size=medium"
    async with session.get(url, headers={"Authorization": PEXELS_API_KEY}) as response:
        response_content = await response.json()
        return response_content


async def generate_video(scene):
    async with aiohttp.ClientSession() as session:
        response_content = await fetch_video(session, scene)
        blob_storage_array = []
        if len(response_content["videos"]) > 0:
            video_link = None
            for video in response_content["videos"][0]["video_files"]:
                if video["quality"] == "hd":
                    video_link = video["link"]
                    break
            if not video_link:
                video_link = response_content["videos"][0]["video_files"][0]["link"]
            async with session.get(video_link) as video_response:
                video_data = await video_response.read()
                current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                blob_name = f"{scene}_{current_time}_{str(uuid4())}"
                src_url = uploadFile(video_data, blob_name, folder='video', file_type="video")
                blob_storage_array.append(src_url)
        return blob_storage_array


@app.post("/generateVideo")
async def generate_video_handler(VideoBody: VideoBody):
    tasks = [generate_video(scene) for scene in VideoBody.scene]
    results = await asyncio.gather(*tasks)
    return {"video": [url for urls in results for url in urls]}


class MovieBody(BaseModel):
    audio: str
    srt_file: str
    video: List[str]
    subtitles: List[str]


def split_text(text: str):
    words = text.split()
    lines = []
    current_line = ''

    for word in words:
        if len(current_line + ' ' + word) <= 50:
            if current_line == '':
                current_line = word
            else:
                current_line += ' ' + word
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return '\n'.join(lines)


def annotate(clip, txt: str, txt_color="white", fontsize=75, font="Arial-Bold", blur=False, start=0, duration=None):
    txt = split_text(txt)
    txtclip = editor.TextClip(txt, fontsize=fontsize, font=font, color=txt_color)
    txtclip = txtclip.set_pos(("center", clip.h - txtclip.h - 150))
    txtclip = txtclip.set_start(start + 0.001)

    if duration is not None:
        txtclip = txtclip.set_duration(duration)

    if blur:
        blur_size = 5
        blur_txtclip = editor.TextClip(txt, fontsize=fontsize, font=font, color="black")
        blur_txtclip = blur_txtclip.set_pos(
            (
                (clip.w - blur_txtclip.w) // 2 + blur_size,
                clip.h - blur_txtclip.h - (150 - blur_size),
            )
        )
        blur_txtclip = blur_txtclip.set_start(start + 0.001)
        if duration is not None:
            blur_txtclip = blur_txtclip.set_duration(duration)

        cvc = editor.CompositeVideoClip([clip, blur_txtclip, txtclip])
    else:
        cvc = editor.CompositeVideoClip([clip, txtclip])
    return cvc.set_duration(clip.duration)


def calculate_text_similarity(text1, text2):
    # Create a Differ instance
    differ = difflib.Differ()

    # Compare the texts
    diff = differ.compare(text1.split(), text2.split())

    # Calculate the similarity ratio
    similarity_ratio = difflib.SequenceMatcher(None, text1, text2).ratio()

    return similarity_ratio


def resizer(pic, newsize):
    newsize = list(map(int, newsize))[::-1]
    shape = pic.shape

    pilim = Image.fromarray(pic)
    resized_pil = pilim.resize(newsize[::-1], Image.LANCZOS)
    # arr = np.fromstring(resized_pil.tostring(), dtype='uint8')
    # arr.reshape(newshape)
    return np.array(resized_pil)


@app.post("/fakeVideo")
async def fakeVideo():
    videoArr = [
        "http://res.cloudinary.com/dhm7d2jq6/video/upload/v1712407042/video/commercial%20kitchen%20upgrade_2024-04-06_20-37-15_b728cba9-0311-4331-a719-68d92540902b.mp4",
        "http://res.cloudinary.com/dhm7d2jq6/video/upload/v1712407094/video/energy-efficient%20equipment%20showcase_2024-04-06_20-38-03_7bdf3352-6090-4386-9c2c-1dfa086c33a3.mp4",
    ]
    videoList = []
    for idx, video in enumerate(videoArr):
        tempFile = f"./temp_{idx}.mp4"
        with open(tempFile, 'wb') as f:
            videoResponse = requests.get(video)
            f.write(videoResponse.content)
            f.close()
        tempVideo = editor.VideoFileClip(tempFile)
        tempVideo = tempVideo.loop(duration=3)
        tempVideo = tempVideo.set_fps(30)
        tempVideo = tempVideo.fl_image(lambda pic: resizer(pic.astype('uint8'), (1920, 1080)))
        videoList.append(tempVideo)
        os.remove(tempFile)
    final_clip = editor.concatenate_videoclips(videoList)

    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    blob_name = f"final_{current_time}_{generate_uuid()}.mp4"
    final_clip.write_videofile(blob_name, fps=30, codec="libx264", audio_codec="aac")
    with open(blob_name, 'rb') as f:
        data = f.read()
        f.close()
    src_url = uploadFile(data, blob_name, folder='final', file_type="video")
    return {"final": src_url}


def cut_sentences(movie_body: MovieBody):
    print("Before:", movie_body)
    new_subtitles = []
    new_videos = []
    for vid, sub in zip(movie_body.video, movie_body.subtitles):
        cur_len = 0
        prev_i = 0
        sub_split = sub.split(' ')
        for i, word in enumerate(sub_split):
            cur_len += len(word)
            if (i == len(sub_split) - 1) or (i < len(sub_split) - 1 and cur_len + len(sub_split[i + 1]) > 70):
                new_subtitles.append(' '.join(sub_split[prev_i : i + 1]))
                new_videos.append(vid)
                prev_i = i + 1
                cur_len = 0

    movie_body.video = new_videos
    movie_body.subtitles = new_subtitles

    return movie_body


@app.post("/stitchVideos")
async def stitchVideos(MovieBody: MovieBody):
    MovieBody = cut_sentences(MovieBody)
    print(MovieBody)

    srt_file_response = requests.get(MovieBody.srt_file)
    srt_file = srt_file_response.content.decode("utf-8")
    srt_parse = list(srt.parse(srt_file))

    min_window = []
    for srt_content in srt_parse:
        start = srt_content.start
        end = srt_content.end
        duration = end - start

        content = srt_content.content

        content = re.sub(r'\W', '', content)

        min_window += [0] * len(content)
        min_window[-1] = [duration, len(content)]

    rightest = -1
    for i in range(len(min_window) - 1, -1, -1):
        if min_window[i] == 0:
            min_window[i] = rightest
        else:
            rightest = min_window[i]

    left_pad = 0
    new_video = []
    subs = []
    for idx, subtitle in enumerate(MovieBody.subtitles):
        dur = timedelta(seconds=0)

        alpha_len = len(re.sub(r'\W', '', subtitle))
        for i in range(alpha_len):
            if left_pad + i >= len(min_window):
                break
            data_point = min_window[left_pad + i]
            dur += data_point[0] / data_point[1]

        left_pad += alpha_len

        if len(subs) > 0:
            currentStart = subs[-1][0][0]
        else:
            currentStart = timedelta(seconds=0)

        if dur.total_seconds() <= 3:
            dur += timedelta(seconds=0.5)

        subs.append(([[currentStart, currentStart + dur], subtitle]))
        new_video.append(MovieBody.video[idx])

    videoList = []

    max_idx = 0
    for idx, video in enumerate(new_video):
        if idx < max_idx:
            continue

        tempFile = f"./temp_{idx}.mp4"
        with open(tempFile, 'wb') as f:
            videoResponse = requests.get(video)
            f.write(videoResponse.content)
            f.close()

        right_idx = idx
        total_duration = 0
        while (right_idx < len(new_video)) and (new_video[right_idx] == new_video[idx]):
            total_duration += subs[right_idx][0][1].total_seconds()
            right_idx += 1

        duration = subs[int(idx)][0][1] - subs[int(idx)][0][0]
        tempVideo = editor.VideoFileClip(video)
        tempVideo = tempVideo.loop(duration=total_duration)
        tempVideo = tempVideo.set_fps(30)
        tempVideo = tempVideo.fl_image(lambda pic: resizer(pic.astype('uint8'), (1920, 1080)))

        right_idx = idx
        total_duration = 0
        while (right_idx < len(new_video)) and (new_video[right_idx] == new_video[idx]):
            print("start", subs[int(right_idx)][0][0])
            print("sub:", subs[int(right_idx)][1])
            tempVideo = annotate(
                tempVideo,
                subs[right_idx][1],
                blur=True,
                start=total_duration,
                duration=subs[right_idx][0][1].total_seconds(),
            )
            print("end", subs[int(right_idx)][0][1])
            total_duration += subs[right_idx][0][1].total_seconds()
            right_idx += 1

        max_idx = max(max_idx, right_idx)
        os.remove(tempFile)
        videoList.append(tempVideo)

    print("Processing Audio & Music")
    print(MovieBody.audio)
    audio = editor.AudioFileClip(MovieBody.audio)

    final_clip = editor.concatenate_videoclips(videoList)
    final_clip = final_clip.set_audio(audio)

    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    blob_name = f"final_{current_time}_{generate_uuid()}.mp4"
    final_clip.write_videofile(
        blob_name, fps=30, codec="libx264", audio_codec="aac", temp_audiofile="temp-audio.m4a", remove_temp=True
    )
    with open(blob_name, 'rb') as f:
        data = f.read()
        f.close()

    src_url = uploadFile(data, blob_name, folder='final', file_type="video")
    return {"final": src_url}
