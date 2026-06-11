"""
배틀그라운드 전장 배경 및 고지 점령 아이템 매칭 규칙이 결합된 play_gui.py (assets 폴더 경로 완벽 수정본)
"""

import os
import sys
import random
import tkinter as tk
from tkinter import messagebox

# 필수 라이브러리(Pillow) 자동 예외 및 로드 처리
try:
    from PIL import Image, ImageTk
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageTk

# 기존 game.py 호환 로드
from game import GameEnv, BOARD_SIZE, Card
from agent import DynamicDifficultyAgent

MODEL_PATH = "model.pkl"

class GameGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("턴제 전략 게임 - 배틀그라운드 에디션")
        self.root.geometry("800x600")
        self.root.resizable(False, False)

        self.agent = DynamicDifficultyAgent(epsilon=0.0, epsilon_min=0.0)
        if os.path.exists(MODEL_PATH):
            self.agent.load(MODEL_PATH)
            self.agent.epsilon = 0.1
            self.agent.epsilon_min = 0.05
        else:
            self.agent.epsilon = 1.0

        self.env = None
        self.selected_map = None

        # [핵심 수정] 기준 실행 디렉터리 설정
        self.base_dir = os.path.dirname(os.path.abspath(__file__))

        # 외부 game.py 클래스 변형 에러 방지를 위한 자체 아이템 위치 제어 메커니즘
        self.item_positions = {}

        self.bg_image_tk = None
        self.canvas = None

        self.create_lobby_ui()

    def find_image_path(self, map_name_eng):
        """
        [핵심 경로 엔진]
        1) assets/images/ 폴더 내부 우선 탐색
        2) 파일명 및 확장자의 대소문자(png, PNG, Erangel, erangel) 조합을 모두 체크하여 유연하게 매칭합니다.
        """
        # 탐색할 후보 디렉터리 목록 (assets/images/ 폴더 및 현재 폴더)
        search_dirs = [
            os.path.join(self.base_dir, "assets", "images"),
            os.path.join(self.base_dir, "assets"),
            self.base_dir
        ]

        # 파일명 조합 후보들
        names = [map_name_eng, map_name_eng.lower(), map_name_eng.capitalize(), map_name_eng.upper()]
        extensions = [".png", ".PNG", ".jpeg", ".JPEG", ".jpg", ".JPG"]

        for d in search_dirs:
            if not os.path.exists(d):
                continue
            for n in names:
                for ext in extensions:
                    full_path = os.path.join(d, n + ext)
                    if os.path.exists(full_path):
                        return full_path
        return ""

    def create_lobby_ui(self):
        self.clear_window()

        title_label = tk.Label(self.root, text="⚡ 턴제 전략 보드게임 ⚡", font=("Helvetica", 24, "bold"))
        title_label.pack(pady=40)

        subtitle_label = tk.Label(self.root, text="플레이할 맵(전장)을 선택하세요!", font=("Helvetica", 14))
        subtitle_label.pack(pady=10)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=30)

        # 버튼 한글 표기와 내부 파일 매핑용 영문 명칭
        maps_info = [("에란겔", "erangel"), ("미라마", "miramar"), ("사녹", "sanhok"), ("비켄디", "vikendi")]
        colors = ["#4CAF50", "#FFC107", "#2196F3", "#9C27B0"]

        for (m_kor, m_eng), c in zip(maps_info, colors):
            btn = tk.Button(
                btn_frame,
                text=m_kor,
                font=("Helvetica", 14, "bold"),
                width=12,
                height=2,
                bg=c,
                fg="white",
                command=lambda kor=m_kor, eng=m_eng: self.start_game(kor, eng)
            )
            btn.pack(side=tk.LEFT, padx=10)

        desc_text = "💡 전장 규칙: 집 카드와 보급 카드는 시작 시 1~50칸 사이에 랜덤 배치됩니다.\n해당 칸에 정확히 도달 시 자동으로 획득하며, 매 턴 카드를 쓰거나 1칸 이동할 수 있습니다."
        desc_label = tk.Label(self.root, text=desc_text, font=("Helvetica", 11), fg="gray")
        desc_label.pack(side=tk.BOTTOM, pady=40)

    def init_map_items(self):
        """각 플레이어별 아이템 배치 정보 초기화 (AttributeError 원천 차단)"""
        self.item_positions = {}
        for pid in range(2):
            h_pos = random.randint(1, BOARD_SIZE - 1)
            s_pos = random.randint(1, BOARD_SIZE - 1)
            while h_pos == s_pos:
                s_pos = random.randint(1, BOARD_SIZE - 1)

            self.item_positions[pid] = {
                "home_pos": h_pos,
                "supply_pos": s_pos,
                "home_card": Card(card_type="home", value=random.randint(10, 35)),
                "supply_card": Card(card_type="supply", value=random.randint(20, 45))
            }
            # 시작할 때 기본 제공되던 강제 5장 손패를 비우고 게임 규칙 반영
            if hasattr(self.env, 'players') and len(self.env.players) > pid:
                self.env.players[pid].hand = []

    def check_item_pickup(self, pid) -> list:
        """플레이어가 이동한 후 해당 칸에 아이템이 있는지 검사하고 획득 처리"""
        messages = []
        p_state = self.env.players[pid]
        items = self.item_positions[pid]

        if len(p_state.hand) >= 7: # MAX_HAND 제한
            return messages

        # 집 카드 밟았는지 확인
        if items["home_card"] is not None and p_state.position == items["home_pos"]:
            p_state.hand.append(items["home_card"])
            messages.append(f"🏠 [{p_state.name}] {p_state.position}칸에서 '집 카드(+{items['home_card'].value})' 획득!")
            items["home_card"] = None

        # 보급 카드 밟았는지 확인
        if items["supply_card"] is not None and p_state.position == items["supply_pos"]:
            p_state.hand.append(items["supply_card"])
            messages.append(f"📦 [{p_state.name}] {p_state.position}칸에서 '보급 카드(+{items['supply_card'].value})' 획득!")
            items["supply_card"] = None

        return messages

    def start_game(self, map_kor, map_eng):
        self.selected_map = map_kor
        self.clear_window()

        # [수정] 다중 경로 추적기를 활용해 assets 폴더 내 이미지를 안전하게 로딩
        img_path = self.find_image_path(map_eng)

        # Canvas 레이아웃 생성
        self.canvas = tk.Canvas(self.root, width=800, height=600)
        self.canvas.pack(fill="both", expand=True)

        # 이미지 가비지 컬렉션 더블 로킹 바인딩
        if img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img = img.resize((800, 600), Image.Resampling.LANCZOS)

                self.bg_image_tk = ImageTk.PhotoImage(img)
                self.canvas.bg_image = self.bg_image_tk # 가비지 컬렉션 방지 영구 참조 결속

                self.canvas.create_image(0, 0, image=self.bg_image_tk, anchor="nw")
            except Exception as e:
                self.canvas.config(bg="#e0e0e0")
                self.canvas.create_text(400, 30, text=f"[이미지 로드 실패 예외: {e}]", fill="red", font=("Helvetica", 11, "bold"))
        else:
            self.canvas.config(bg="#e0e0e0")
            # 탐색 실패시 디버깅을 돕기 위해 예상 기본 탐색 경로 출력
            fail_path = os.path.join(self.base_dir, "assets", "images", f"{map_eng}.png")
            self.canvas.create_text(400, 50, text=f"[배경 파일을 찾을 수 없음]\n아래 위치에 파일이 존재하는지 확인바랍니다:\n{fail_path}", fill="red", font=("Helvetica", 11, "bold"), justify=tk.CENTER)

        # UI 판넬 디자인 배치
        self.status_frame = tk.Frame(self.root, bg="white", bd=2, relief="solid")
        self.canvas.create_window(400, 160, window=self.status_frame, width=720, height=220)

        self.status_label = tk.Label(self.status_frame, text="", font=("Courier", 11), bg="white", justify=tk.LEFT)
        self.status_label.pack(padx=10, pady=10, fill="both", expand=True)

        self.action_frame = tk.Frame(self.root, bg="#333333", padx=10, pady=10)
        self.canvas.create_window(400, 480, window=self.action_frame, width=720, height=80)

        self.action_buttons = []

        # 백엔드 엔진 모델 연동 및 초기화
        self.env = GameEnv(num_players=2, human_ids=[0])
        self.env.reset()
        self.init_map_items()

        self.update_ui()

    def update_ui(self):
        if self.env.done:
            self.end_game()
            return

        me = self.env.players[0]
        opp = self.env.players[1]

        p_bar = "-" * (me.position // 2)
        ai_bar = "-" * (opp.position // 2)

        p_items_info = self.item_positions.get(0, {"home_pos":0, "supply_pos":0, "home_card":None, "supply_card":None})
        ai_items_info = self.item_positions.get(1, {"home_pos":0, "supply_pos":0, "home_card":None, "supply_card":None})

        p_items = f"🏠집: {p_items_info['home_pos']}칸 | 📦보급: {p_items_info['supply_pos']}칸" if (p_items_info['home_card'] or p_items_info['supply_card']) else "모두 획득함"
        ai_items = f"🏠집: {ai_items_info['home_pos']}칸 | 📦보급: {ai_items_info['supply_pos']}칸" if (ai_items_info['home_card'] or ai_items_info['supply_card']) else "모두 획득함"

        status_text = (
            f"🌐 전장: {self.selected_map} 모드\n"
            f"====================================================================\n"
            f"🙋‍♂️ 당신 (P1 남은 거리: {me.position}칸) -> 배치된 아이템 칸: [{p_items}]\n"
            f"   {p_bar}📍\n"
            f"🤖 AI   (P2 남은 거리: {opp.position}칸) -> 배치된 아이템 칸: [{ai_items}]\n"
            f"   {ai_bar}📍\n"
            f"====================================================================\n"
            f"🃏 현재 내 보관 손패: {me.hand}\n"
            f"📦 보급 카드 필살기 사용 여부: {'사용함(불가)' if me.supply_used else '미사용(가능)'}"
        )
        self.status_label.config(text=status_text)

        for btn in self.action_buttons:
            btn.destroy()
        self.action_buttons.clear()

        valid_actions = self.env.get_valid_actions(0)
        action_map = {0: "이동 (1칸)", 1: "집 카드 사용", 2: "보급 카드 사용", 3: "카드 뽑기"}

        for act in valid_actions:
            btn = tk.Button(
                self.action_frame,
                text=action_map[act],
                font=("Helvetica", 11, "bold"),
                width=14,
                height=2,
                command=lambda a=act: self.player_step(a)
            )
            btn.pack(side=tk.LEFT, padx=10, expand=True)
            self.action_buttons.append(btn)

    def player_step(self, action):
        # 1. 플레이어 이동 처리
        _, done, _ = self.env.step(0, action)

        # 아이템 획득 이벤트 트리거링 및 알림
        pickup_msgs = self.check_item_pickup(0)
        if pickup_msgs:
            messagebox.showinfo("아이템 획득!", "\n".join(pickup_msgs))

        if done:
            self.update_ui()
            return

        # 2. 인공지능 강화학습 피드백 연산 및 턴 진행
        state = self.env.get_state(1)
        valid = self.env.get_valid_actions(1)
        ai_action = self.agent.choose_action(state, valid)

        win_prob = self.agent.predict_win_prob(state, valid)
        ai_action_names = {0: "이동", 1: "집카드", 2: "보급카드", 3: "카드뽑기"}

        _, done, _ = self.env.step(1, ai_action)

        # AI 아이템 실시간 탐지 획득 연산
        ai_pickup_msgs = self.check_item_pickup(1)

        ai_msg = f"🤖 AI가 [{ai_action_names[ai_action]}] 행동을 선택했습니다!\n(AI 예측 승률: {win_prob:.1%})"
        if ai_pickup_msgs:
            ai_msg += "\n\n💥 " + "\n".join(ai_pickup_msgs)

        messagebox.showinfo("AI의 턴 결과", ai_msg)
        self.update_ui()

    def end_game(self):
        player_won = self.env.winner == 0
        self.agent.record_result(ai_won=not player_won)
        diff_msg = self.agent.adjust_difficulty()

        if player_won:
            result_msg = f"🎉 승리했습니다! 전장을 지배하셨습니다."
        else:
            result_msg = f"🤖 AI 승리! 다음 판에는 아이템 칸을 적극 선점해 보세요."

        if diff_msg:
            result_msg += f"\n\n📢 난이도 조정 알림: {diff_msg}"

        answer = messagebox.askyesno("게임 종료", f"{result_msg}\n\n다시 플레이하시겠습니까?")
        if answer:
            self.create_lobby_ui()
        else:
            self.root.quit()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = GameGUI(root)
    root.mainloop()