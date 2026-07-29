# -*- coding: utf-8 -*-
"""背单词 —— 摸鱼友好的极简记忆卡片（CustomTkinter 版）

快捷键：
    空格          显示中文
    回车 / →      认识了，下一个
    ←             没记住，下一个
    Esc           立刻隐藏窗口（老板键）
    Ctrl+Alt+W    全局呼出 / 隐藏
    Ctrl+T        在「录入」页用大模型翻译当前单词
"""
import csv
import json
import os
import random
import re
import struct
import sys
import threading
import time
import tkinter as tk
import urllib.request
import urllib.error
from collections import deque
from contextlib import contextmanager
from datetime import date, timedelta
from tkinter import filedialog, messagebox

import customtkinter as ctk
from dotenv import load_dotenv

try:
    import keyboard  # 全局热键（老板键呼出）
except Exception:    # 兜底：没有 keyboard 库也能正常用
    keyboard = None

# .env 跟着 exe/脚本放，方便分发
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    load_dotenv(dotenv_path=os.path.join(_BASE_DIR, '.env'))
except OSError:
    pass

APP_NAME = '背单词'
HOTKEY = 'ctrl+alt+w'
FONT = 'Microsoft YaHei UI'

GREEN = '#2fa572'
RED = '#e0453a'


def resource_path(rel):
    """打包后从临时目录读资源，源码运行时读脚本目录。"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def data_path(name):
    """数据文件放在 exe（或脚本）旁边，保证单文件分发时数据不丢。"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


WORDS_FILE = data_path('words.json')
STATS_FILE = data_path('stats.json')
MAX_NATIVE_MESSAGE_BYTES = 4096
WORD_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-]*$")


@contextmanager
def file_lock(path):
    """用单独的锁文件协调 GUI 和 Native Host 的跨进程写入。"""
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


def _load_json_unlocked(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _save_json_unlocked(path, obj):
    temp_path = f'{path}.{os.getpid()}.{threading.get_ident()}.tmp'
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def load_json(path, default):
    return _load_json_unlocked(path, default)


def save_json(path, obj):
    try:
        with file_lock(path):
            _save_json_unlocked(path, obj)
    except Exception:
        pass


def call_llm(en):
    """调用本机 .env 配置的大模型；扩展侧不会获得任何凭证。"""
    url = os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    url += '/chat/completions'
    model = os.getenv('LLM_MODEL', 'gpt-4o-mini')
    body = {
        'model': model,
        'temperature': 0,
        'max_tokens': 300,
        'messages': [
            {'role': 'system',
             'content': '你是英译中助手，只输出最简洁直接的中文释义，'
                        '不要解释、不要引号、不要多余符号、不要思考过程。'},
            {'role': 'user', 'content': f'翻译成中文：{en}'},
        ],
    }
    if os.getenv('LLM_DISABLE_THINKING', 'true').lower() in ('true', '1', 'yes'):
        body['reasoning_effort'] = 'low'
        body['enable_thinking'] = False
    req = urllib.request.Request(
        url, data=json.dumps(body).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {os.getenv("LLM_API_KEY")}'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    text = data['choices'][0]['message']['content'].strip()
    for ch in ('"', "'", '「', '」', '"', '"', '：', ':'):
        text = text.strip().strip(ch)
    return text.splitlines()[0].strip() or en


def _native_error(code, message):
    return {'status': 'error', 'code': code, 'message': message}


def _read_native_message(stream):
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError('消息头不完整')
    length = struct.unpack('<I', header)[0]
    if length > MAX_NATIVE_MESSAGE_BYTES:
        raise ValueError('消息过长')
    payload = stream.read(length)
    if len(payload) != length:
        raise ValueError('消息体不完整')
    return json.loads(payload.decode('utf-8'))


def _write_native_message(stream, message):
    payload = json.dumps(message, ensure_ascii=False).encode('utf-8')
    stream.write(struct.pack('<I', len(payload)))
    stream.write(payload)
    stream.flush()


def _validate_native_request(message):
    if not isinstance(message, dict) or message.get('type') != 'translate':
        return None, _native_error('WORD_INVALID', '请求格式不正确')
    english = message.get('english')
    if not isinstance(english, str):
        return None, _native_error('WORD_INVALID', '英文必须是文本')
    english = english.strip()
    if not 1 <= len(english) <= 64 or not WORD_PATTERN.fullmatch(english):
        return None, _native_error('WORD_INVALID', '仅支持 1–64 个英文字符的单词或短语')
    return english, None


def _upsert_native_word(english, chinese):
    with file_lock(WORDS_FILE):
        words = _load_json_unlocked(WORDS_FILE, [])
        if not isinstance(words, list):
            words = []
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
        _save_json_unlocked(WORDS_FILE, words)
    return added


def _redact_error(message):
    text = str(message)
    secret = os.getenv('LLM_API_KEY', '')
    if secret:
        text = text.replace(secret, '[REDACTED]')
    return text[:240]


def _handle_native_request(message, last_request_at):
    english, error = _validate_native_request(message)
    if error:
        return error, last_request_at
    now = time.monotonic()
    if last_request_at is not None and now - last_request_at < 1.0:
        return _native_error('RATE_LIMITED', '请稍等 1 秒后再试'), last_request_at
    last_request_at = now
    if not os.getenv('LLM_API_KEY'):
        return _native_error('NO_API_KEY', '本机未配置 LLM_API_KEY'), last_request_at
    try:
        chinese = call_llm(english)
        added = _upsert_native_word(english, chinese)
        return {
            'status': 'ok', 'english': english, 'chinese': chinese, 'added': added
        }, last_request_at
    except urllib.error.HTTPError as exc:
        return _native_error(
            f'LLM_HTTP_{exc.code}', f'翻译服务返回 HTTP {exc.code}'
        ), last_request_at
    except (TimeoutError, urllib.error.URLError) as exc:
        return _native_error('LLM_TIMEOUT', _redact_error(exc)), last_request_at
    except Exception as exc:
        return _native_error('INTERNAL', _redact_error(exc)), last_request_at


def native_host_loop():
    """Chrome Native Messaging 主循环：4 字节小端长度 + UTF-8 JSON。"""
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    last_request_at = None
    while True:
        try:
            message = _read_native_message(input_stream)
            if message is None:
                return
            response, last_request_at = _handle_native_request(
                message, last_request_at
            )
            _write_native_message(output_stream, response)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _write_native_message(
                output_stream,
                _native_error('WORD_INVALID', _redact_error(exc)),
            )
            return


class App:
    def __init__(self):
        ctk.set_appearance_mode('system')      # 跟随系统深浅色
        ctk.set_default_color_theme('blue')

        self.win = ctk.CTk()
        self.win.title(APP_NAME)
        self.win.minsize(520, 600)
        try:
            self.win.iconbitmap(resource_path('icon.ico'))
        except Exception:
            pass
        self._center(600, 660)

        self.words = load_json(WORDS_FILE, [])
        self._word_snapshot = {
            word.get('id'): dict(word) for word in self.words
            if isinstance(word, dict) and word.get('id') is not None
        }
        self._round_queue = deque(self._build_round_order(self.words))
        self._round_ids = set(self._round_queue)
        self._round_completed = False
        self._words_signature = self._get_words_signature()
        self.stats = load_json(STATS_FILE, {'total': 0, 'days': {}})
        self.current = None        # 当前正在复习的单词
        self.revealed = False      # 当前单词是否已显示中文
        self.mini = False          # 是否处于迷你模式
        self.normal_geometry = None
        self.mini_geometry = None
        self._drag = None
        self._toast_after = None
        self._list_dirty = False
        self._sync_stop = threading.Event()

        self._build_ui()
        self._bind_shortcuts()
        self._register_hotkey()
        self.win.protocol('WM_DELETE_WINDOW', self.on_close)

        self.show_word(pick_new=True)
        self._update_mini_button()
        self._sync_thread = threading.Thread(
            target=self._watch_external_words,
            name='words-file-watcher',
            daemon=True,
        )
        self._sync_thread.start()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.main = ctk.CTkFrame(self.win, fg_color='transparent')
        self.main.pack(fill='both', expand=True)

        # 顶栏：标题 + 提示 + 迷你模式按钮
        header = ctk.CTkFrame(self.main, fg_color='transparent')
        header.pack(fill='x', padx=16, pady=(12, 4))
        ctk.CTkLabel(header, text='📖 背单词',
                     font=(FONT, 20, 'bold')).pack(side='left')
        ctk.CTkLabel(header, text=f'Esc 隐藏 · Ctrl+Alt+W 呼出',
                     font=(FONT, 11), text_color='gray60').pack(side='right', padx=(0, 8))
        self.btn_mini = ctk.CTkButton(
            header, text='迷你模式', width=80, height=28,
            font=(FONT, 12), command=self.enter_mini)
        self.btn_mini.pack(side='right')

        # 四个标签页
        self.tabview = ctk.CTkTabview(self.main, corner_radius=12,
                                      segmented_button_selected_color=('#1f6aa5', '#1f6aa5'))
        self.tabview.pack(fill='both', expand=True, padx=12, pady=(4, 12))
        for name in ('背单词', '录入', '列表', '统计'):
            self.tabview.add(name)
        try:  # 切换标签时刷新对应页面（包裹 CTk 自己的切换回调，不能直接覆盖）
            seg = self.tabview._segmented_button
            orig_cmd = seg._command

            def _tab_cmd(name, _orig=orig_cmd):
                if callable(_orig):
                    _orig(name)          # 先让 CTk 完成页面切换
                self._on_tab_change(name)  # 再刷新对应页面内容

            seg.configure(command=_tab_cmd)
        except Exception:
            pass

        self._build_review_tab(self.tabview.tab('背单词'))
        self._build_add_tab(self.tabview.tab('录入'))
        self._build_list_tab(self.tabview.tab('列表'))
        self._build_stats_tab(self.tabview.tab('统计'))
        self._build_mini_frame()

    def _build_review_tab(self, tab):
        self.review_empty = ctk.CTkLabel(tab, text='还没有单词\n去「录入」添加几个吧',
                                         font=(FONT, 16), text_color='gray60', justify='center')

        self.review_complete = ctk.CTkFrame(tab, fg_color='transparent')
        ctk.CTkLabel(
            self.review_complete, text='🎉 本轮完成',
            font=(FONT, 28, 'bold')).pack(pady=(72, 8))
        self.lbl_round_complete = ctk.CTkLabel(
            self.review_complete, text='', font=(FONT, 14),
            text_color='gray60', justify='center')
        self.lbl_round_complete.pack(pady=(0, 22))
        ctk.CTkButton(
            self.review_complete, text='开始下一轮',
            font=(FONT, 15, 'bold'), width=180, height=42,
            command=self.start_new_round).pack(pady=4)
        ctk.CTkLabel(
            self.review_complete,
            text='迷你模式已暂停，开始下一轮后会重新启用',
            font=(FONT, 11), text_color='gray50').pack(pady=10)

        self.review_body = ctk.CTkFrame(tab, fg_color='transparent')
        self.review_body.pack(fill='both', expand=True)

        # 卡片
        self.card = ctk.CTkFrame(self.review_body, corner_radius=18)
        self.card.pack(fill='both', expand=True, padx=18, pady=(14, 10))

        self.lbl_en = ctk.CTkLabel(self.card, text='', font=(FONT, 38, 'bold'),
                                   wraplength=440, justify='center')
        self.lbl_en.pack(expand=True, pady=(36, 0))

        self.lbl_cn = ctk.CTkLabel(self.card, text='', font=(FONT, 24),
                                   text_color=('#1f6aa5', '#4c9fe0'),
                                   wraplength=440, justify='center')
        self.lbl_cn.pack(expand=True, pady=(0, 36))

        # 按钮区（两种状态切换）
        self.btns_hidden = ctk.CTkFrame(self.review_body, fg_color='transparent')
        self.btn_reveal = ctk.CTkButton(self.btns_hidden, text='显示中文  (空格)',
                                        font=(FONT, 14), height=40, width=200,
                                        command=self.reveal)
        self.btn_reveal.pack(pady=2)

        self.btns_revealed = ctk.CTkFrame(self.review_body, fg_color='transparent')
        ctk.CTkButton(self.btns_revealed, text='✗ 没记住  (←)', font=(FONT, 14),
                      height=40, width=140, fg_color='transparent', border_width=1,
                      border_color=RED, text_color=RED, hover_color=('#fbeae9', '#3a2221'),
                      command=lambda: self.grade(False)).pack(side='left', padx=8)
        ctk.CTkButton(self.btns_revealed, text='✓ 认识了  (回车)', font=(FONT, 14),
                      height=40, width=140,
                      command=lambda: self.grade(True)).pack(side='left', padx=8)

        ctk.CTkLabel(self.review_body,
                     text='空格 显示  ·  回车 认识  ·  ← 没记住（排到队尾）  ·  Esc 隐藏',
                     font=(FONT, 11), text_color='gray60').pack(pady=(2, 8))

    def _build_add_tab(self, tab):
        box = ctk.CTkFrame(tab, fg_color='transparent')
        box.pack(fill='x', padx=36, pady=(40, 0))

        # 英语单词：标签行（左侧标签 + 右侧快捷键提示）
        lab_row = ctk.CTkFrame(box, fg_color='transparent')
        lab_row.pack(fill='x')
        ctk.CTkLabel(lab_row, text='英语单词', font=(FONT, 13),
                     anchor='w').pack(side='left')
        ctk.CTkLabel(lab_row, text='Ctrl+T 自动翻译', font=(FONT, 10),
                     text_color='gray50').pack(side='right')

        # 输入行：英文输入框 + 内嵌翻译按钮（输入-动作一体）
        en_row = ctk.CTkFrame(box, fg_color='transparent')
        en_row.pack(fill='x', pady=(4, 16))
        self.entry_en = ctk.CTkEntry(en_row, font=(FONT, 15), height=42,
                                     placeholder_text='例如：serendipity')
        self.entry_en.pack(side='left', fill='x', expand=True)
        self.btn_translate = ctk.CTkButton(
            en_row, text='翻译', font=(FONT, 14), width=84, height=42,
            fg_color=('#e3f0fb', '#16324a'),
            text_color=('#1f6aa5', '#6fb7f0'),
            hover_color=('#cfe5f8', '#1e4261'),
            command=self.translate_current)
        self.btn_translate.pack(side='right', padx=(8, 0))

        ctk.CTkLabel(box, text='中文翻译', font=(FONT, 13), anchor='w').pack(fill='x')
        self.entry_cn = ctk.CTkEntry(box, font=(FONT, 15), height=42,
                                     placeholder_text='点右侧「翻译」或手动填写')
        self.entry_cn.pack(fill='x', pady=(4, 24))
        self.entry_en.bind('<Return>', lambda e: self.save_word())
        self.entry_cn.bind('<Return>', lambda e: self.save_word())

        # 通栏主按钮，表单视觉重心
        ctk.CTkButton(box, text='保 存', font=(FONT, 15, 'bold'), height=44,
                      command=self.save_word).pack(fill='x')
        self.lbl_toast = ctk.CTkLabel(box, text='', font=(FONT, 13))
        self.lbl_toast.pack(pady=10)

    def _build_list_tab(self, tab):
        top = ctk.CTkFrame(tab, fg_color='transparent')
        top.pack(fill='x', padx=10, pady=(10, 4))
        self.entry_search = ctk.CTkEntry(top, font=(FONT, 13), height=34,
                                         placeholder_text='🔍 搜索单词或翻译…')
        self.entry_search.pack(fill='x')
        self.entry_search.bind('<KeyRelease>', lambda e: self.render_list())

        self.list_frame = ctk.CTkScrollableFrame(tab, corner_radius=10)
        self.list_frame.pack(fill='both', expand=True, padx=10, pady=6)

        bottom = ctk.CTkFrame(tab, fg_color='transparent')
        bottom.pack(fill='x', padx=10, pady=(2, 8))
        self.lbl_count = ctk.CTkLabel(bottom, text='', font=(FONT, 12), text_color='gray60')
        self.lbl_count.pack(side='left')
        ctk.CTkButton(bottom, text='导出', width=64, height=28, font=(FONT, 12),
                      fg_color='transparent', border_width=1, border_color='gray50',
                      text_color=('gray20', 'gray90'),
                      command=self.export_words).pack(side='right', padx=(6, 0))
        ctk.CTkButton(bottom, text='导入', width=64, height=28, font=(FONT, 12),
                      fg_color='transparent', border_width=1, border_color='gray50',
                      text_color=('gray20', 'gray90'),
                      command=self.import_words).pack(side='right')

    def _build_stats_tab(self, tab):
        grid = ctk.CTkFrame(tab, fg_color='transparent')
        grid.pack(fill='x', padx=10, pady=(14, 6))
        grid.columnconfigure((0, 1), weight=1, uniform='c')

        self.stat_cards = {}
        for key, caption in (('words', '总单词数'), ('reviews', '总复习次数'),
                             ('today', '今日复习'), ('streak', '连续打卡（天）')):
            card = ctk.CTkFrame(grid, corner_radius=14)
            r, c = divmod(len(self.stat_cards), 2)
            card.grid(row=r, column=c, padx=6, pady=6, sticky='nsew')
            val = ctk.CTkLabel(card, text='0', font=(FONT, 28, 'bold'))
            val.pack(pady=(14, 0))
            ctk.CTkLabel(card, text=caption, font=(FONT, 12),
                         text_color='gray60').pack(pady=(0, 12))
            self.stat_cards[key] = val

        chart = ctk.CTkFrame(tab, corner_radius=14)
        chart.pack(fill='both', expand=True, padx=16, pady=(4, 12))
        ctk.CTkLabel(chart, text='最近 7 天复习量', font=(FONT, 13, 'bold'),
                     anchor='w').pack(fill='x', padx=14, pady=(12, 4))
        self.chart_box = ctk.CTkFrame(chart, fg_color='transparent')
        self.chart_box.pack(fill='x', padx=14, pady=(0, 12))

    def _build_mini_frame(self):
        """迷你置顶模式：无边框小窗，只留单词和两个评分键。"""
        self.mini_frame = ctk.CTkFrame(self.win, corner_radius=0, border_width=1,
                                       border_color='gray40')
        self.mini_frame.bind('<Button-1>', self._drag_start)
        self.mini_frame.bind('<B1-Motion>', self._drag_move)

        top = ctk.CTkFrame(self.mini_frame, fg_color='transparent', height=22)
        top.pack(fill='x')
        ctk.CTkLabel(top, text='⠿ 拖动', font=(FONT, 10),
                     text_color='gray50').pack(side='left', padx=6)
        ctk.CTkButton(top, text='✕', width=22, height=22, font=(FONT, 11),
                      fg_color='transparent', text_color='gray60', hover_color=('#e8e8e8', '#3a3a3a'),
                      command=self.exit_mini).pack(side='right', padx=2, pady=2)

        self.mini_en = ctk.CTkLabel(self.mini_frame, text='', font=(FONT, 21, 'bold'),
                                    cursor='hand2', wraplength=300)
        self.mini_en.pack(pady=(0, 0))
        self.mini_en.bind('<Button-1>', lambda e: self.reveal())
        self.mini_cn = ctk.CTkLabel(self.mini_frame, text='', font=(FONT, 13),
                                    text_color=('#1f6aa5', '#4c9fe0'), wraplength=300)
        self.mini_cn.pack()

        row = ctk.CTkFrame(self.mini_frame, fg_color='transparent')
        row.pack(pady=(4, 8))
        ctk.CTkButton(row, text='✗', width=44, height=26, font=(FONT, 13),
                      fg_color='transparent', border_width=1, border_color=RED, text_color=RED,
                      hover_color=('#fbeae9', '#3a2221'),
                      command=lambda: self.grade(False)).pack(side='left', padx=4)
        ctk.CTkButton(row, text='✓', width=44, height=26, font=(FONT, 13),
                      command=lambda: self.grade(True)).pack(side='left', padx=4)

    # ------------------------------------------------------------- shortcuts
    def _bind_shortcuts(self):
        self.win.bind('<space>', lambda e: self._key_reveal())
        self.win.bind('<Return>', lambda e: self._key_known())
        self.win.bind('<Right>', lambda e: self._key_known())
        self.win.bind('<Left>', lambda e: self._key_unknown())
        self.win.bind('<Escape>', lambda e: self.hide_window())
        self.win.bind('<Control-t>', lambda e: self.translate_current())

    def _in_entry(self):
        return isinstance(self.win.focus_get(), (tk.Entry, ctk.CTkEntry))

    def _review_context(self):
        """只有在背单词标签页或迷你模式里，复习快捷键才生效。"""
        return self.mini or (self.tabview.get() == '背单词')

    def _key_reveal(self):
        if not self._in_entry() and self._review_context():
            self.reveal()

    def _key_known(self):
        if not self._in_entry() and self._review_context():
            if self.revealed:
                self.grade(True)

    def _key_unknown(self):
        if not self._in_entry() and self._review_context():
            if self.revealed:
                self.grade(False)

    # ----------------------------------------------------------------- data
    @staticmethod
    def _get_words_signature():
        try:
            stat = os.stat(WORDS_FILE)
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _watch_external_words(self):
        """在后台检测文件变化，避免占用 Tk/Windows 窗口消息循环。"""
        observed_signature = self._words_signature
        while not self._sync_stop.wait(0.75):
            try:
                signature = self._get_words_signature()
                if signature == observed_signature:
                    continue
                observed_signature = signature
                incoming = _load_json_unlocked(WORDS_FILE, [])
                if not isinstance(incoming, list):
                    continue
                self.win.after(
                    0,
                    lambda sig=signature, words=incoming:
                    self._apply_external_words(sig, words),
                )
            except Exception:
                pass

    def _apply_external_words(self, signature, incoming):
        """只在 Tk 主线程应用已确认的词库变化。"""
        if signature != self._get_words_signature():
            return
        self._words_signature = signature
        if incoming == self.words:
            return
        old_word_ids = {
            word.get('id') for word in self.words
            if isinstance(word, dict) and word.get('id') is not None
        }
        current_id = (
            self.current.get('id') if isinstance(self.current, dict) else None
        )
        self.words = incoming
        incoming_ids = {
            word.get('id') for word in incoming
            if isinstance(word, dict) and word.get('id') is not None
        }
        self._round_ids.intersection_update(incoming_ids)
        self._round_queue = deque(
            word_id for word_id in self._round_queue
            if word_id in incoming_ids
        )
        if not self._round_completed:
            new_ids = incoming_ids - old_word_ids
            self._round_ids.update(new_ids)
            self._round_queue.extend(
                word.get('id') for word in incoming
                if word.get('id') in new_ids
            )
        self._word_snapshot = {
            word.get('id'): dict(word) for word in incoming
            if isinstance(word, dict) and word.get('id') is not None
        }
        if current_id is not None:
            self.current = next(
                (word for word in incoming if word.get('id') == current_id),
                None,
            )
        if self.current is None and incoming:
            self.current = self.pick_word()
            self.revealed = False
        if self.tabview.get() == '列表':
            self.render_list()
            self._list_dirty = False
        else:
            self._list_dirty = True
        self._update_mini_button()
        self.refresh_review_ui()

    def save_words(self):
        try:
            with file_lock(WORDS_FILE):
                disk_words = _load_json_unlocked(WORDS_FILE, [])
                if not isinstance(disk_words, list):
                    disk_words = []
                disk_by_id = {
                    word.get('id'): word for word in disk_words
                    if isinstance(word, dict) and word.get('id') is not None
                }
                merged = []
                seen = set()
                for word in self.words:
                    word_id = word.get('id')
                    base = self._word_snapshot.get(word_id)
                    disk = disk_by_id.get(word_id)
                    chosen = (
                        disk if disk is not None and base is not None
                        and word == base and disk != base
                        else word
                    )
                    merged.append(chosen)
                    seen.add(word_id)
                for word in disk_words:
                    word_id = word.get('id')
                    if word_id not in seen and word_id not in self._word_snapshot:
                        merged.append(word)
                _save_json_unlocked(WORDS_FILE, merged)
                self.words = merged
                self._word_snapshot = {
                    word.get('id'): dict(word) for word in merged
                    if isinstance(word, dict) and word.get('id') is not None
                }
                self._words_signature = self._get_words_signature()
        except Exception:
            pass

    def save_stats(self):
        save_json(STATS_FILE, self.stats)

    def record_review(self):
        today = date.today().isoformat()
        days = self.stats.setdefault('days', {})
        days[today] = days.get(today, 0) + 1
        self.stats['total'] = self.stats.get('total', 0) + 1
        self.save_stats()

    @staticmethod
    def _build_round_order(words):
        """创建新一轮的随机队列。"""
        word_ids = [
            word.get('id') for word in words
            if isinstance(word, dict) and word.get('id') is not None
        ]
        random.shuffle(word_ids)
        return word_ids

    def pick_word(self):
        """返回队首单词；不会的词会在评分时重新进入队尾。"""
        words_by_id = {
            word.get('id'): word for word in self.words
            if isinstance(word, dict) and word.get('id') is not None
        }
        while self._round_queue and self._round_queue[0] not in words_by_id:
            self._round_queue.popleft()
        return words_by_id.get(self._round_queue[0]) if self._round_queue else None

    def _advance_round_queue(self, reviewed_id, known):
        """认识则出队；不会则移到队尾。"""
        self._round_queue = deque(
            word_id for word_id in self._round_queue
            if word_id != reviewed_id
        )
        if (
            not known
            and reviewed_id in self._round_ids
            and any(word.get('id') == reviewed_id for word in self.words)
        ):
            self._round_queue.append(reviewed_id)

    # --------------------------------------------------------------- review
    def _update_mini_button(self):
        if not hasattr(self, 'btn_mini'):
            return
        available = bool(self.words) and not self._round_completed
        if available:
            if not self.btn_mini.winfo_manager():
                self.btn_mini.pack(side='right')
        else:
            self.btn_mini.pack_forget()

    def start_new_round(self):
        self._round_queue = deque(self._build_round_order(self.words))
        self._round_ids = set(self._round_queue)
        self._round_completed = False
        self.current = None
        self._update_mini_button()
        self.show_word(pick_new=True)

    def _complete_round(self):
        self.current = None
        self.revealed = False
        self._round_completed = bool(self._round_ids)
        if self.mini:
            self.exit_mini()
        self._update_mini_button()
        self.refresh_review_ui()

    def _on_tab_change(self, name=None):
        name = name or self.tabview.get()
        if name == '列表':
            self.render_list()
            self._list_dirty = False
        elif name == '统计':
            self.render_stats()
        elif name == '背单词':
            self.refresh_review_ui()

    def show_word(self, pick_new=True):
        if pick_new or self.current is None:
            self.current = self.pick_word()
        self.revealed = False
        self.refresh_review_ui()

    def refresh_review_ui(self):
        has = self.current is not None
        self.review_empty.pack_forget()
        self.review_complete.pack_forget()
        if self._round_completed and self.words:
            self.review_body.pack_forget()
            self.lbl_round_complete.configure(
                text=f'本轮已通过 {len(self._round_ids)} 个单词\n可以休息一下了')
            self.review_complete.pack(fill='both', expand=True)
        elif has:
            self.review_empty.pack_forget()
            if not self.review_body.winfo_ismapped():
                self.review_body.pack(fill='both', expand=True)
            self.lbl_en.configure(text=self.current['english'])
            self.lbl_cn.configure(text=self.current['chinese'] if self.revealed else '')
            self.btns_revealed.pack_forget()
            self.btns_hidden.pack_forget()
            (self.btns_revealed if self.revealed else self.btns_hidden).pack(pady=2)
        else:
            self.review_body.pack_forget()
            self.review_empty.pack(expand=True, pady=80)
        if self.mini:
            self.mini_en.configure(text=self.current['english'] if has else '暂无单词')
            self.mini_cn.configure(text=(self.current['chinese']
                                         if (has and self.revealed) else ''))

    def reveal(self):
        if self.current and not self.revealed:
            self.revealed = True
            self.refresh_review_ui()

    def grade(self, known):
        if not self.current:
            return
        reviewed_id = self.current.get('id')
        if known:
            self.current['lastReviewed'] = int(time.time() * 1000)
            self.current['reviewCount'] = self.current.get('reviewCount', 0) + 1
        # 没记住：不更新复习时间，并将它移动到本轮队尾。
        self._advance_round_queue(reviewed_id, known)
        self.record_review()
        self.save_words()
        if self._round_queue:
            self.show_word(pick_new=True)
        else:
            self._complete_round()

    # ------------------------------------------------------------------ add
    def translate_current(self):
        en = self.entry_en.get().strip()
        if not en:
            self.toast('先填入要翻译的单词', RED)
            return
        if not os.getenv('LLM_API_KEY'):
            self.toast('未配置 LLM_API_KEY（见 .env）', RED)
            return
        if not getattr(self, '_translating', False):
            self._translating = True
            self.btn_translate.configure(state='disabled', text='翻译中…')
            self.toast('翻译中…', '#1f6aa5')
            threading.Thread(target=self._do_translate, args=(en,), daemon=True).start()

    def _do_translate(self, en):
        try:
            result = self._call_llm(en)
            self.win.after(0, lambda: self._on_translate_done(result))
        except urllib.error.HTTPError as e:
            # 把服务端返回的报错正文读出来，方便判断 env/服务端问题
            try:
                detail = e.read().decode('utf-8', 'replace').strip()
            except Exception:
                detail = ''
            err = f'HTTP {e.code}: {detail[:200]}' if detail else f'HTTP {e.code}'
            self.win.after(0, lambda: self._on_translate_done(None, err))
        except Exception as e:
            err = f'{type(e).__name__}: {e}' or '翻译失败'
            self.win.after(0, lambda: self._on_translate_done(None, err))

    def _on_translate_done(self, result, err=None):
        self._translating = False
        self.btn_translate.configure(state='normal', text='翻译')
        if err:
            self.toast(f'翻译失败：{err}', RED)
            return
        # 已切换走/清空了输入框就不再覆盖焦点干扰
        self.entry_cn.delete(0, 'end')
        self.entry_cn.insert(0, result)
        self.entry_cn.focus_set()
        self.toast('✓ 已翻译', GREEN)

    @staticmethod
    def _call_llm(en):
        return call_llm(en)

    def save_word(self):
        en = self.entry_en.get().strip()
        cn = self.entry_cn.get().strip()
        if not en or not cn:
            self.toast('请填写完整', RED)
            return
        if any(w['english'].lower() == en.lower() for w in self.words):
            self.toast('这个单词已存在', RED)
            return
        self.words.append({
            'id': int(time.time() * 1000) * 1000 + random.randint(0, 999),
            'english': en,
            'chinese': cn,
            'createdAt': int(time.time() * 1000),
            'lastReviewed': None,
            'reviewCount': 0,
        })
        new_id = self.words[-1]['id']
        if not self._round_completed:
            self._round_ids.add(new_id)
            self._round_queue.append(new_id)
        self.save_words()
        self.entry_en.delete(0, 'end')
        self.entry_cn.delete(0, 'end')
        self.entry_en.focus_set()
        self.toast('✓ 已保存', GREEN)

    def toast(self, msg, color):
        self.lbl_toast.configure(text=msg, text_color=color)
        if self._toast_after:
            self.win.after_cancel(self._toast_after)
        self._toast_after = self.win.after(2000, lambda: self.lbl_toast.configure(text=''))

    # ----------------------------------------------------------------- list
    def render_list(self):
        for child in self.list_frame.winfo_children():
            child.destroy()

        kw = self.entry_search.get().strip().lower()
        shown = [w for w in sorted(self.words, key=lambda x: x.get('createdAt', 0), reverse=True)
                 if not kw or kw in w['english'].lower() or kw in w['chinese'].lower()]

        if not shown:
            ctk.CTkLabel(self.list_frame, text='没有匹配的单词' if kw else '还没有单词',
                         font=(FONT, 14), text_color='gray60').pack(pady=40)
        for w in shown:
            row = ctk.CTkFrame(self.list_frame, fg_color='transparent')
            row.pack(fill='x', pady=1)
            info = ctk.CTkFrame(row, fg_color='transparent')
            info.pack(side='left', fill='x', expand=True)
            head = ctk.CTkFrame(info, fg_color='transparent')
            head.pack(fill='x')
            ctk.CTkLabel(head, text=w['english'], font=(FONT, 14, 'bold'),
                         anchor='w').pack(side='left')
            ctk.CTkLabel(head, text='  ' + w['chinese'], font=(FONT, 13),
                         text_color='gray60', anchor='w').pack(side='left')
            last = w.get('lastReviewed')
            meta = (time.strftime('%m/%d %H:%M', time.localtime(last / 1000))
                    if last else '从未复习')
            ctk.CTkLabel(info, text=f"复习 {w.get('reviewCount', 0)} 次 · 上次 {meta}",
                         font=(FONT, 10), text_color='gray50',
                         anchor='w').pack(fill='x')
            ctk.CTkButton(row, text='✕', width=30, height=26, font=(FONT, 12),
                          fg_color='transparent', text_color=RED,
                          hover_color=('#fbeae9', '#3a2221'),
                          command=lambda wid=w['id']: self.delete_word(wid)).pack(side='right')

        total = len(self.words)
        self.lbl_count.configure(text=f'共 {total} 个单词' +
                                 (f' · 筛选出 {len(shown)} 个' if kw else ''))

    def delete_word(self, wid):
        if not messagebox.askyesno('确认删除', '确定要删除这个单词吗？', parent=self.win):
            return
        self.words = [w for w in self.words if w['id'] != wid]
        self._round_ids.discard(wid)
        self._round_queue = deque(
            word_id for word_id in self._round_queue if word_id != wid
        )
        if self.current and self.current['id'] == wid:
            self.current = None
        self.save_words()
        self.render_list()
        if self._round_queue:
            self.show_word(pick_new=True)
        elif self.words and self._round_ids:
            self._complete_round()
        else:
            self._round_completed = False
            self._update_mini_button()
            self.show_word(pick_new=True)

    # ---------------------------------------------------------- import/export
    def import_words(self):
        path = filedialog.askopenfilename(
            parent=self.win, title='导入单词',
            filetypes=[('单词文件', '*.json *.csv'), ('JSON', '*.json'), ('CSV', '*.csv')])
        if not path:
            return
        try:
            items = self._parse_import(path)
        except Exception as e:
            messagebox.showerror('导入失败', f'文件解析失败：\n{e}', parent=self.win)
            return
        if not items:
            messagebox.showinfo('导入', '文件里没有可导入的单词', parent=self.win)
            return

        existing = {w['english'].lower() for w in self.words}
        added = 0
        now = int(time.time() * 1000)
        for en, cn in items:
            if en.lower() in existing:
                continue
            existing.add(en.lower())
            word_id = now * 1000 + random.randint(0, 999)
            self.words.append({
                'id': word_id,
                'english': en, 'chinese': cn,
                'createdAt': now, 'lastReviewed': None, 'reviewCount': 0,
            })
            if not self._round_completed:
                self._round_ids.add(word_id)
                self._round_queue.append(word_id)
            added += 1
        self.save_words()
        self.render_list()
        messagebox.showinfo('导入完成',
                            f'新增 {added} 个单词，跳过重复 {len(items) - added} 个',
                            parent=self.win)

    @staticmethod
    def _parse_import(path):
        ext = os.path.splitext(path)[1].lower()
        items = []
        if ext == '.json':
            data = load_json(path, [])
            if isinstance(data, dict):
                data = data.get('words', [])
            for w in data:
                en = str(w.get('english', '')).strip()
                cn = str(w.get('chinese', '')).strip()
                if en and cn:
                    items.append((en, cn))
        else:
            with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                for row in csv.reader(f):
                    if len(row) < 2:
                        continue
                    en, cn = row[0].strip(), row[1].strip()
                    if not en or not cn:
                        continue
                    if en.lower() in ('english', 'en', 'word', '单词'):
                        continue  # 跳过表头
                    items.append((en, cn))
        return items

    def export_words(self):
        if not self.words:
            messagebox.showinfo('导出', '还没有单词可以导出', parent=self.win)
            return
        path = filedialog.asksaveasfilename(
            parent=self.win, title='导出单词', initialfile='words_backup',
            defaultextension='.json',
            filetypes=[('JSON', '*.json'), ('CSV', '*.csv')])
        if not path:
            return
        try:
            if path.lower().endswith('.csv'):
                with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['english', 'chinese', 'createdAt',
                                     'lastReviewed', 'reviewCount'])
                    for w in self.words:
                        writer.writerow([w['english'], w['chinese'], w.get('createdAt'),
                                         w.get('lastReviewed'), w.get('reviewCount', 0)])
            else:
                save_json(path, self.words)
        except Exception as e:
            messagebox.showerror('导出失败', str(e), parent=self.win)
            return
        messagebox.showinfo('导出完成', f'已导出 {len(self.words)} 个单词到：\n{path}',
                            parent=self.win)

    # ---------------------------------------------------------------- stats
    def render_stats(self):
        days = self.stats.get('days', {})
        today = date.today()
        self.stat_cards['words'].configure(text=str(len(self.words)))
        self.stat_cards['reviews'].configure(text=str(self.stats.get('total', 0)))
        self.stat_cards['today'].configure(text=str(days.get(today.isoformat(), 0)))
        self.stat_cards['streak'].configure(text=str(self._streak(days)))

        for child in self.chart_box.winfo_children():
            child.destroy()
        seq = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
        counts = [days.get(d.isoformat(), 0) for d in seq]
        peak = max(counts) or 1
        for d, n in zip(seq, counts):
            row = ctk.CTkFrame(self.chart_box, fg_color='transparent')
            row.pack(fill='x', pady=1)
            label = '今天' if d == today else f'{d.month}/{d.day}'
            ctk.CTkLabel(row, text=label, font=(FONT, 11), width=44,
                         anchor='w', text_color='gray60').pack(side='left')
            bar = ctk.CTkProgressBar(row, height=10)
            bar.pack(side='left', fill='x', expand=True, padx=6)
            bar.set(n / peak if n else 0)
            ctk.CTkLabel(row, text=str(n), font=(FONT, 11), width=28,
                         text_color='gray60').pack(side='right')

    @staticmethod
    def _streak(days):
        d = date.today()
        if days.get(d.isoformat(), 0) == 0:
            d -= timedelta(days=1)  # 今天还没学， streak 从昨天算
        n = 0
        while days.get(d.isoformat(), 0) > 0:
            n += 1
            d -= timedelta(days=1)
        return n

    # ------------------------------------------------------------ mini mode
    def enter_mini(self):
        if self.mini or self._round_completed or self.current is None:
            return
        self.mini = True
        self.normal_geometry = self.win.geometry()
        self.main.pack_forget()
        self.mini_frame.pack(fill='both', expand=True)
        self.win.minsize(1, 1)  # 先解除最小尺寸限制，窗口才能缩小
        self.win.overrideredirect(True)
        self.win.geometry(self.mini_geometry or '340x150+260+260')
        self.win.attributes('-topmost', True)
        self.refresh_review_ui()

    def exit_mini(self):
        if not self.mini:
            return
        self.mini_geometry = self.win.geometry()
        self.mini = False
        self.mini_frame.pack_forget()
        self.main.pack(fill='both', expand=True)
        self.win.overrideredirect(False)
        self.win.minsize(520, 600)
        self.win.attributes('-topmost', False)
        if self.normal_geometry:
            self.win.geometry(self.normal_geometry)
        self.refresh_review_ui()

    def _drag_start(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag_move(self, e):
        if self._drag:
            self.win.geometry(f'+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}')

    # ------------------------------------------------------------- boss key
    def _register_hotkey(self):
        if keyboard is None:
            return
        try:
            keyboard.add_hotkey(HOTKEY, lambda: self.win.after(0, self.toggle_visibility))
            self._hotkey_ok = True
        except Exception:
            self._hotkey_ok = False

    def toggle_visibility(self):
        if self.win.state() == 'withdrawn':
            self.show_window()
        else:
            self.hide_window()

    def hide_window(self):
        if getattr(self, '_hotkey_ok', False):
            self.win.withdraw()           # 彻底藏起来，任务栏也看不到
        else:
            self.win.iconify()            # 没有全局热键时退化为最小化

    def show_window(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.win.attributes('-topmost', True)
        self.win.after(150, lambda: self.win.attributes('-topmost', self.mini))

    # ----------------------------------------------------------------- misc
    def _center(self, w, h):
        self.win.update_idletasks()
        x = (self.win.winfo_screenwidth() - w) // 2
        y = max(30, (self.win.winfo_screenheight() - h) // 2 - 30)
        self.win.geometry(f'{w}x{h}+{x}+{y}')

    def on_close(self):
        self._sync_stop.set()
        if keyboard is not None:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.win.destroy()

    def run(self):
        self.win.mainloop()


if __name__ == '__main__':
    executable_name = os.path.basename(sys.executable).casefold()
    if '--host' in sys.argv or '背单词-host' in executable_name:
        native_host_loop()
    else:
        App().run()
