import warnings
warnings.filterwarnings("ignore", message=".*pin_memory.*")

import os
import sys
import time
import pyautogui
import threading
import queue
import cv2
import easyocr
import numpy as np
import win32gui
import win32ui
import win32con
import win32api
import win32clipboard
from win32com.client import Dispatch
from openai import OpenAI

_api_key = os.getenv("OPENAI_API_KEY", "").strip()
_base_url = os.getenv("OPENAI_BASE_URL", "https://aigc-api.aitoolcore.com/api/v1").strip()

if not _api_key:
    print("错误：未设置 OPENAI_API_KEY 环境变量。请在终端执行：")
    print('  set OPENAI_API_KEY=你的密钥   (Windows CMD)')
    print('  $env:OPENAI_API_KEY="你的密钥"  (Windows PowerShell)')
    print('  export OPENAI_API_KEY=你的密钥  (Linux/Mac)')
    sys.exit(1)

# 大模型接口配置（密钥从环境变量读取，不再写在源码里）
client = OpenAI(
    api_key=_api_key,
    base_url=_base_url
)

# AI对话上下文
ai_messages = [{"role": "system", "content": "你是西华师范大学小助手，名字叫西华小妹儿。只回答学校相关的问题。回答不要超过500个字。无关问题只说「不好意思，我只回答学校相关的问题哦~」"}]
answer_queue = queue.Queue()
is_answering = False

# ========== 任务栏横向搜索带（应对录屏时图标被麦克风挤位）==========
# 原锁定区域太小：(2184, 1389, 33, 29)，录屏时图标横向位移就会匹配失败
# 现在扩大为右侧 200 像素宽的搜索带，允许图标在任务栏右侧左右浮动
qqIconRegion = (2050, 1373, 220, 50)
# 任务栏区域：2115,1373 ~ 2559,1439
scRegion = (2115, 1373, 444, 66)
# 输入法图标区域：2223,1389 ~ 2261,1419
inputRegion = (2223, 1389, 38, 30)

# OCR与头像识别配置
reader = easyocr.Reader(["ch_sim","en"], gpu=False)
FACE_TEMPLATE_PATH = "face.png"
DEFAULT_AVATAR_MIN_R = 20
DEFAULT_AVATAR_MAX_R = 45
AVATAR_R_TOLERANCE = 0.25
CONTENT_TOP_GAP = 10
CONTENT_BOTTOM_PAD = 100
AVATAR_TO_TEXT_OFFSET = 40
CONTENT_RIGHT_PAD = 20
CHAT_LEFT_FROM_ADDUSER_X = 20
CHAT_TOP_FROM_ADDUSER_Y = 80
CAHT_BOTTOM_FROM_HISTORY_Y = -100
_EXPECTED_AVATAR_RADIUS = None

# 语音播报
spk = Dispatch("SAPI.SpVoice")

# ========== win32 API截图函数，替代PIL ImageGrab，解决截图卡死问题 ==========
def capture_screen(region=None):
    if region:
        left, top, width, height = region
    else:
        left, top = 0, 0
        width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
    hdc = win32gui.GetDC(0)
    mfc_dc = win32ui.CreateDCFromHandle(hdc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)
    save_dc.BitBlt((0, 0), (width, height), mfc_dc, (left, top), win32con.SRCCOPY)
    bmpinfo = bitmap.GetInfo()
    bmpstr = bitmap.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype=np.uint8).reshape(bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4)
    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(0, hdc)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

# ========== 模板匹配+尺寸过滤：QQ新消息图标（右下角数字徽标）==========
# 仅靠 cv2.matchTemplate 容易误匹配输入法图标。额外做：(a) 多尺度匹配
# (b) 尺寸过滤（任务栏图标直径 16-40 像素）(c) 非极大值抑制
def find_new_message_icon(region):
    try:
        template = cv2.imread("newGroupMsg.png", cv2.IMREAD_COLOR)
        if template is None:
            return None
        screen_bgr = capture_screen(region)
        if screen_bgr is None or screen_bgr.shape[0] < 10 or screen_bgr.shape[1] < 10:
            return None

        th, tw = template.shape[:2]
        sh, sw = screen_bgr.shape[:2]

        # 多尺度：0.8x / 1.0x / 1.2x
        candidates = []  # (confidence, center_x_rel, center_y_rel)
        for scale in [0.8, 1.0, 1.2]:
            new_w = max(10, int(tw * scale))
            new_h = max(10, int(th * scale))
            if new_w >= sw or new_h >= sh:
                continue
            t_scaled = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            result = cv2.matchTemplate(screen_bgr, t_scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            cx = max_loc[0] + new_w // 2
            cy = max_loc[1] + new_h // 2
            candidates.append((max_val, cx, cy, new_w, new_h))

        if not candidates:
            return None

        # 取最高分
        candidates.sort(key=lambda c: c[0], reverse=True)
        best_val, best_cx, best_cy, best_w, best_h = candidates[0]

        # 尺寸过滤：任务栏图标大小大约 16-40 像素见方
        if best_w < 14 or best_w > 45 or best_h < 14 or best_h > 45:
            return None

        # 置信度阈值：0.20 以下说明完全没匹配到
        if best_val < 0.20:
            return None

        center_x = best_cx + region[0]
        center_y = best_cy + region[1]
        pos = (center_x, center_y)
        print(f"【新消息匹配】坐标：{pos} 置信度：{best_val:.2f} 尺寸：{best_w}x{best_h}")
        return pos
    except Exception as e:
        print(f"【新消息匹配异常】：{e}")
        return None

# ========== 核心：OpenCV模板匹配替代pyautogui，解决全屏截图卡死问题 ==========
def safe_find_by(img, confidence=0.8, region=None):
    try:
        template = cv2.imread(img, cv2.IMREAD_COLOR)
        if template is None:
            print(f"【模板读取失败】{img}")
            return None
        screen_bgr = capture_screen(region)
        result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= confidence:
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            if region:
                center_x += region[0]
                center_y += region[1]
            pos = (center_x, center_y)
            print(f"【成功匹配】{img} 坐标：{pos} 置信度：{max_val:.2f}")
            return pos
        return None
    except Exception as e:
        print(f"【查找异常】{img}：{e}")
        return None

# 图像灰度预处理
def preprocess_gray(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (3, 3), 0)

# 头像模板半径检测
def detect_avatar_radius_from_image(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    gray = preprocess_gray(img)
    min_r = max(8, int(min(w, h)*0.25))
    max_r = int(min(w, h)*0.55)
    circle = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=min(w, h) // 2,
        param1=80,
        param2=20,
        minRadius=min_r,
        maxRadius=max_r
    )
    if circle is None:
        return None
    circles = np.uint16(np.around(circle))
    circles = sorted(circles[0], key=lambda c: c[2], reverse=True)
    return int(circles[0][2])

# 初始化头像半径
def init_expected_avatar_radius():
    global _EXPECTED_AVATAR_RADIUS
    if _EXPECTED_AVATAR_RADIUS is None:
        _EXPECTED_AVATAR_RADIUS = detect_avatar_radius_from_image(FACE_TEMPLATE_PATH)
    return _EXPECTED_AVATAR_RADIUS

# 通过按钮定位聊天区域
def get_chat_region_by_buttons():
    try:
        adduser_pos = safe_find_by("adduser.png")
        history_pos = safe_find_by("history.png")
        if not (adduser_pos and history_pos):
            return None, None
        x1 = int(adduser_pos[0] + CHAT_LEFT_FROM_ADDUSER_X)
        y1 = int(adduser_pos[1] + CHAT_TOP_FROM_ADDUSER_Y)
        x2 = int(history_pos[0])
        y2 = int(history_pos[1] + CAHT_BOTTOM_FROM_HISTORY_Y)
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        width = right - left
        height = bottom - top
        if width > 0 and height > 0:
            return (left, top, width, height), history_pos
        return None, None
    except Exception as e:
        print(e)
        return None, None

# ========== 头像检测：霍夫圆检测，取最底部的圆 ==========
def find_avatar(chat_bgr):
    try:
        exp_r = init_expected_avatar_radius()
        if exp_r:
            min_r = max(10, int(exp_r * (1 - AVATAR_R_TOLERANCE)))
            max_r = max(min_r + 1, int(exp_r * (1 + AVATAR_R_TOLERANCE)))
        else:
            min_r, max_r = DEFAULT_AVATAR_MIN_R, DEFAULT_AVATAR_MAX_R

        gray = preprocess_gray(chat_bgr)
        circle = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=60,
            param1=50,
            param2=22,
            minRadius=min_r,
            maxRadius=max_r
        )
        if circle is not None:
            circles = np.uint16(np.around(circle))
            circles = sorted(circles[0], key=lambda c: c[1], reverse=True)
            return circles[0]
        return None
    except Exception as e:
        print("头像检测异常：", e)
        return None

# 昵称区域
def get_nicename_region(avatar_x, avatar_y, radius):
    x = max(0, avatar_x + AVATAR_TO_TEXT_OFFSET)
    y = max(0, avatar_y - radius - 3)
    return (x, y, 500, 40)

# 消息内容区域（头像右边 → history.png左边，基于标志按钮+偏移量计算）
def get_content_region(chat_region, nickname_region, history_pos):
    chat_l, chat_t, chat_w, chat_h = chat_region
    nick_l, nick_t, nick_w, nick_h = nickname_region
    # 左边界：头像右边（头像X + 半径 + 小偏移）
    c_l = nick_l
    c_t = nick_t + nick_h + CONTENT_TOP_GAP
    # 右边界：history.png 的 X 位置
    c_r = history_pos[0]
    # 下边界：history.png 的 Y 位置
    c_b = history_pos[1]
    c_l = max(chat_l, c_l)
    c_t = max(chat_t, c_t)
    c_r = min(chat_l + chat_w, c_r)
    c_b = min(chat_t + chat_h, c_b)
    if c_r > c_l and c_b > c_t:
        return (c_l, c_t, c_r - c_l, c_b - c_t)
    return None

# OCR文字识别
def ocr(region):
    try:
        if len(region) != 4 or any(x < 0 for x in region):
            return "区域非法"
        img_bgr = capture_screen(region)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=1.1, fy=1.1, interpolation=cv2.INTER_CUBIC)
        res = reader.readtext(gray, detail=0, paragraph=True)
        text = "".join(res).strip()
        return text if text else "识别失败"
    except Exception as e:
        print(e)
        return "识别失败"

# 获取最新消息（头像检测定位头像，内容区域从昵称下方到history.png上方）
def get_last_message():
    init_expected_avatar_radius()
    chat_region, history_pos = get_chat_region_by_buttons()
    if not chat_region:
        return "获取聊天区域失败", ""

    chat_bgr = capture_screen(chat_region)

    avatar = find_avatar(chat_bgr)
    if avatar is not None:
        ax, ay, r = int(avatar[0]), int(avatar[1]), int(avatar[2])
        abs_ax = chat_region[0] + ax
        abs_ay = chat_region[1] + ay
        nick_region = get_nicename_region(abs_ax, abs_ay, r)
        nickname = ocr(nick_region)
        content_region = get_content_region(chat_region, nick_region, history_pos)
        if content_region:
            content = ocr(content_region)
            return f"{nickname}：{content}", content

    # 兜底：只截取聊天区域最底部 80px，宽度从头像右侧到 history.png 左边
    chat_l, chat_t, chat_w, chat_h = chat_region
    fallback_left = chat_l + 120
    fallback_top = chat_t + chat_h - 90
    fallback_right = history_pos[0]
    fallback_bottom = history_pos[1] - 10
    if fallback_right > fallback_left and fallback_bottom > fallback_top:
        fallback_region = (fallback_left, fallback_top, fallback_right - fallback_left, fallback_bottom - fallback_top)
        content = ocr(fallback_region)
        lines = [l.strip() for l in content.replace(";", "\n").replace("；", "\n").split("\n") if l.strip()]
        if len(lines) > 1:
            content = lines[-1]
        return "兜底识别：" + content, content
    return "获取聊天区域失败", ""

# AI回复子线程
def ai_worker(question):
    global is_answering
    try:
        ai_messages.append({"role": "user", "content": question})
        completion = client.chat.completions.create(
            model="qwen3.5-flash",
            messages=ai_messages,
            stream=True
        )
        full_answer = ""
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                full_answer += chunk.choices[0].delta.content
        answer_queue.put(full_answer)
        answer_queue.put(None)
        ai_messages.append({"role": "assistant", "content": full_answer})
    except Exception as e:
        answer_queue.put(f"Error: {str(e)}")
        answer_queue.put(None)
    finally:
        is_answering = False

# 获取AI回复
def get_ai_answer(question):
    global is_answering
    if is_answering:
        return "AI正在回复中"
    is_answering = True
    t = threading.Thread(target=ai_worker, args=(question,), daemon=True)
    t.start()
    full_answer = ""
    while True:
        msg = answer_queue.get()
        if msg is None:
            break
        full_answer += msg
    return full_answer

# ========== 修复2：移除send_btn.png图片校验，直接相对坐标定位，解决尺寸报错 ==========
def get_send_btn_pos():
    history_pos = safe_find_by("history.png")
    if not history_pos:
        return None
    # 基于history按钮向下偏移定位发送按钮区域
    send_btn_x = history_pos[0] - 100
    send_btn_y = history_pos[1] + 150
    return (send_btn_x, send_btn_y)

# 单条消息完整处理流程
def handle_new_message():
    newMessageIcon = find_new_message_icon(qqIconRegion)
    if not newMessageIcon:
        return
    spk.Speak("有消息，正在打开窗口")
    pyautogui.moveTo(newMessageIcon, duration=0.3)
    pyautogui.click()
    time.sleep(2)

    msg_info, pure_msg = get_last_message()
    print(f"\n【OCR识别结果】{msg_info}")
    print(f"【纯净消息】{pure_msg}")
    if not pure_msg or pure_msg == "识别失败":
        spk.Speak("消息识别失败")
        pyautogui.hotkey("ctrl", "w")
        return
    spk.Speak("消息已识别，正在生成回复")

    ai_answer = get_ai_answer(pure_msg)
    print(f"【AI回复】{ai_answer}")
    if not ai_answer or ai_answer.startswith("Error"):
        ai_answer = "抱歉，我暂时无法回答这个问题"

    send_btn_pos = get_send_btn_pos()
    if not send_btn_pos:
        spk.Speak("未找到发送按钮")
        pyautogui.hotkey("ctrl", "w")
        return
    
    # 点击输入框
    input_box_pos = (send_btn_pos[0], send_btn_pos[1] - 120)
    pyautogui.moveTo(input_box_pos, duration=0.3)
    pyautogui.click()
    time.sleep(0.3)

    # 输入法切换
    inputType = safe_find_by("imputType.png", region=inputRegion)
    if inputType:
        spk.Speak("需要切换输入法")
        pyautogui.press("shift")
        time.sleep(0.3)

    # 剪贴板粘贴输入中文（替代pyautogui.write，解决中文乱码*的问题）
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(ai_answer, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)
    pyautogui.press("enter")
    spk.Speak("消息已回复")
    time.sleep(1)

    # 关闭窗口
    pyautogui.hotkey("ctrl", "w")
    time.sleep(1)

# 主循环
def main():
    print("=== QQ自动回复程序启动 ===")
    print("正在监听任务栏QQ新消息...")
    spk.Speak("程序启动")
    
    round_count = 0
    max_rounds = 3
    try:
        while round_count < max_rounds:
            time.sleep(1)
            print("\r正在监听新消息...", end="", flush=True)
            newMessageIcon = find_new_message_icon(qqIconRegion)
            if newMessageIcon:
                round_count += 1
                print(f"\n=== 处理第 {round_count} 轮消息 ===")
                handle_new_message()
                print(f"=== 第 {round_count} 轮处理完成 ===\n")
                time.sleep(5)
    except KeyboardInterrupt:
        print("\n\n用户手动中断程序")
    finally:
        print("\n=== 程序退出 ===")
        spk.Speak("程序退出")

if __name__ == "__main__":
    main()