# -*- coding: utf-8 -*-
"""背单词 Chrome Native Messaging Host（无 GUI/Tk 依赖）。"""
import json
import os
import random
import re
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

from dotenv import load_dotenv


if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env'))
except OSError:
    pass

WORDS_FILE = os.path.join(BASE_DIR, 'words.json')
MAX_MESSAGE_BYTES = 4096
WORD_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-]*$")


@contextmanager
def file_lock(path):
    lock_file = open(f'{path}.lock', 'a+b')
    try:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b'\0')
            lock_file.flush()
        lock_file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        if os.name == 'nt':
            try:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        lock_file.close()


def _load_words():
    try:
        with open(WORDS_FILE, 'r', encoding='utf-8') as file:
            words = json.load(file)
        return words if isinstance(words, list) else []
    except Exception:
        return []


def _save_words(words):
    temp_path = f'{WORDS_FILE}.{os.getpid()}.{threading.get_ident()}.tmp'
    try:
        with open(temp_path, 'w', encoding='utf-8') as file:
            json.dump(words, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, WORDS_FILE)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def call_llm(english):
    url = os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    body = {
        'model': os.getenv('LLM_MODEL', 'gpt-4o-mini'),
        'temperature': 0,
        'max_tokens': 300,
        'messages': [
            {
                'role': 'system',
                'content': '你是英译中助手，只输出最简洁直接的中文释义，'
                           '不要解释、不要引号、不要多余符号、不要思考过程。',
            },
            {'role': 'user', 'content': f'翻译成中文：{english}'},
        ],
    }
    if os.getenv('LLM_DISABLE_THINKING', 'true').lower() in ('true', '1', 'yes'):
        body['reasoning_effort'] = 'low'
        body['enable_thinking'] = False
    request = urllib.request.Request(
        f'{url}/chat/completions',
        data=json.dumps(body).encode('utf-8'),
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {os.getenv("LLM_API_KEY")}',
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode('utf-8'))
    text = data['choices'][0]['message']['content'].strip()
    for character in ('"', "'", '「', '」', '"', '"', '：', ':'):
        text = text.strip().strip(character)
    return text.splitlines()[0].strip() or english


def native_error(code, message):
    return {'status': 'error', 'code': code, 'message': message}


def read_message(stream):
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError('消息头不完整')
    length = struct.unpack('<I', header)[0]
    if length > MAX_MESSAGE_BYTES:
        raise ValueError('消息过长')
    payload = stream.read(length)
    if len(payload) != length:
        raise ValueError('消息体不完整')
    return json.loads(payload.decode('utf-8'))


def write_message(stream, message):
    payload = json.dumps(message, ensure_ascii=False).encode('utf-8')
    stream.write(struct.pack('<I', len(payload)))
    stream.write(payload)
    stream.flush()


def validate_request(message):
    if not isinstance(message, dict) or message.get('type') != 'translate':
        return None, native_error('WORD_INVALID', '请求格式不正确')
    english = message.get('english')
    if not isinstance(english, str):
        return None, native_error('WORD_INVALID', '英文必须是文本')
    english = english.strip()
    if not 1 <= len(english) <= 64 or not WORD_PATTERN.fullmatch(english):
        return None, native_error('WORD_INVALID', '仅支持 1–64 个英文字符的单词或短语')
    return english, None


def upsert_word(english, chinese):
    with file_lock(WORDS_FILE):
        words = _load_words()
        found = next(
            (word for word in words
             if str(word.get('english', '')).casefold() == english.casefold()),
            None,
        )
        added = found is None
        if found is None:
            now_ms = int(time.time() * 1000)
            words.append({
                'id': now_ms * 1000 + random.randint(0, 999),
                'english': english,
                'chinese': chinese,
                'createdAt': now_ms,
                'lastReviewed': None,
                'reviewCount': 0,
            })
        else:
            found['english'] = english
            found['chinese'] = chinese
        _save_words(words)
    return added


def redact_error(error):
    text = str(error)
    secret = os.getenv('LLM_API_KEY', '')
    if secret:
        text = text.replace(secret, '[REDACTED]')
    return text[:240]


def handle_request(message, last_request_at):
    english, error = validate_request(message)
    if error:
        return error, last_request_at
    now = time.monotonic()
    if last_request_at is not None and now - last_request_at < 1.0:
        return native_error('RATE_LIMITED', '请稍等 1 秒后再试'), last_request_at
    last_request_at = now
    if not os.getenv('LLM_API_KEY'):
        return native_error('NO_API_KEY', '本机未配置 LLM_API_KEY'), last_request_at
    try:
        chinese = call_llm(english)
        return {
            'status': 'ok',
            'english': english,
            'chinese': chinese,
            'added': upsert_word(english, chinese),
        }, last_request_at
    except urllib.error.HTTPError as error:
        return native_error(
            f'LLM_HTTP_{error.code}', f'翻译服务返回 HTTP {error.code}'
        ), last_request_at
    except (TimeoutError, urllib.error.URLError) as error:
        return native_error('LLM_TIMEOUT', redact_error(error)), last_request_at
    except Exception as error:
        return native_error('INTERNAL', redact_error(error)), last_request_at


def main():
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    last_request_at = None
    while True:
        try:
            message = read_message(input_stream)
            if message is None:
                return
            response, last_request_at = handle_request(message, last_request_at)
            write_message(output_stream, response)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            write_message(
                output_stream,
                native_error('WORD_INVALID', redact_error(error)),
            )
            return


if __name__ == '__main__':
    main()
