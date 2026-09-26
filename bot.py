import os
import discord
from discord.ext import tasks #[M1-3]
import db
from dotenv import load_dotenv #固定名
from datetime import datetime,time,timedelta # delta:時間の差分・幅
from zoneinfo import ZoneInfo #日本時間（JST）設定
import random
import glob #ファイルパスのパターンに一致するファイル一覧を取得する標準ライブラリ
import io        # メモリ上でファイルのように扱える入れ物(BytesIO)。画像を一時的に持つのに使う
import asyncio   # asyncio.to_thread = 重い処理を別スレッドで動かして、Bot全体を止めないようにする
from PIL import Image, ImageEnhance, ImageDraw, ImageFont   # Pillow(画像処理ライブラリ)。縮小・モザイク・明るさ調整・文字描画に使う
import matplotlib
matplotlib.use("Agg")   # ← ここでバックエンドを指定
import matplotlib.pyplot as plt   # ← この時点で初めてバックエンドが確定する(グラフ描画ライブラリ（pltで使うのが慣習)
import matplotlib.dates as mdates #日付の表示形式を細かく指定
from matplotlib.figure import Figure   # pyplotを使わずにグラフを作る道具。別スレッドで作っても、!data のグラフ(pyplot)と干渉しない
plt.rcParams['font.family'] = 'Hiragino Sans' #日本語対応デフォ
#-----------------------------------------------------------------------------------------------------
WEEKDAY_SET = {"月":0, "火":1, "水":2, "木":3, "金":4, "土":5, "日":6} #辞書 plan用(l130~)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CH_ID = int(os.getenv("NOTIFY_CHANNEL_ID"))
MY_USER_ID = int(os.getenv("MY_USER_ID"))
JST = ZoneInfo("Asia/Tokyo")
REM_HOUR = 18
TOMO_HOUR = 21
# REM_TIME = time(hour=18, minute=0, tzinfo=JST)  #リマインダー(18:00)
# PLAN_TIME = time(hour=21, minute=0, tzinfo=JST) #明日の予定(21:00)

EXERCISE_BODY_PART = {
    "ダンベルプレス": "胸",
    "インクライム": "胸",
    "チェストプレス": "胸",
    "ロウマシン": "背中",
    "懸垂マシン": "背中",
    "インクラインダンベル": "背中",
    "ダンベルスクワット": "脚",
    "ダンベル屈伸": "脚",
    "リニアレッグプレス":"脚",
    "ダンベルショルダー": "肩",
    "アーノルドプレス": "肩"
}
DEFO_SETS = 5

# ---- 経験値(XP)・レベル・称号(バッジ)の設定 ----
XP_PER_EXERCISE = 10       # 種目を1つ記録するごと
XP_DAILY_BONUS = 20        # その日の最初の記録ボーナス(来た日ボーナス)
XP_PR_BONUS = 30           # 自己ベストを更新した種目ごと
XP_STREAK_PER_DAY = 5      # 連続記録ボーナス: 連続日数 × この値(その日の最初の記録の時だけ)
XP_STREAK_MAX_DAYS = 7     # 連続記録ボーナスの対象にする連続日数の上限(7日 → 最大35XP)
# 称号: (必要なレベル, 絵文字, 名前, ロールの色)。レベルが上がると、この順に称号がもらえる
BADGES = [
    (5,  "🥉", "ブロンズ", 0xcd7f32),
    (10, "🥈", "シルバー", 0xc0c0c0),
    (15, "🥇", "ゴールド", 0xffd700),
    (20, "💎", "ダイヤ",   0x66e0ff),
    (30, "👑", "クラウン", 0xffb347),
]

# ---- ログインボーナスの設定 ----
LOGIN_PULLS = 5                  # 1日に押せる回数(1回目・3回目・5回目を特別にする案は次の改修で)
# 報酬: (出やすさ(重み), 種類, 経験値, 表示)。重みの合計が100なので、そのまま「%」として読める(図鑑の画像=4%)
#  平均すると1回あたり約3XP(1日で約30XP)。記録して貯める経験値より少なくなるように調整している
LOGIN_REWARDS = [
    (55, "xp",    1,  "⭐ +1XP"),
    (25, "xp",    3,  "⭐ +3XP"),
    (12, "xp",    5,  "✨ +5XP"),
    (4,  "image", 0,  "🖼️ 図鑑の画像"),
    (3,  "xp",    20, "🎉 大当たり！ +20XP"),
    (1,  "xp",    50, "👑 超大当たり！！ +50XP"),
]
LOGIN_IMAGE_FALLBACK_XP = 10     # 図鑑がコンプリート済みで、あげる画像が無い時は、代わりにこの経験値

# ---- 勲章(実績)の設定 ----
# 部位マスター: 部位 → (絵文字, ロールの色)。その部位の記録が BODY_MASTER_COUNT 件に達すると、サーバーの「ロール」ももらえる
BODY_MASTERS = {
    "胸":   ("💪", 0xe74c3c),
    "背中": ("🦅", 0x3498db),
    "脚":   ("🦵", 0x2ecc71),
    "肩":   ("🏔️", 0xe67e22),
}
BODY_MASTER_COUNT = 15
# 勲章: (キー, 絵文字, 名前, 何の数字で判定するか, 目標の数)   目標が None の勲章 = 「図鑑の画像を全部集める」(目標=画像の総数)
#  ※一度もらった勲章は、後で記録を消してもなくならない(獲得したことを badges_earned テーブルに残す)
ACHIEVEMENTS = [
    ("streak3",  "🔥", "三日坊主卒業",   "streak",   3),
    ("streak7",  "🔥", "一週間の炎",     "streak",   7),
    ("streak14", "⚡", "二週間の鉄人",   "streak",   14),
    ("streak30", "🌋", "30日の鬼",       "streak",   30),
    ("gym10",    "🏃", "ジム常連",       "gym_days", 10),
    ("gym30",    "🏠", "ジムが実家",     "gym_days", 30),
    ("gym100",   "🗿", "ジムの主",       "gym_days", 100),
    ("pr5",      "📈", "成長の証",       "pr",       5),
    ("pr20",     "🚀", "限界突破",       "pr",       20),
    ("pr50",     "🌟", "更新マニア",     "pr",       50),
    ("rec50",    "🧱", "積み上げ50",     "records",  50),
    ("rec200",   "🏗️", "積み上げ200",    "records",  200),
    ("rec500",   "🏰", "積み上げ500",    "records",  500),
    ("var5",     "🎯", "いろいろ挑戦",   "variety",  5),
    ("var10",    "🧭", "種目コレクター", "variety",  10),
    ("gal10",    "🖼️", "図鑑見習い",     "gallery",  10),
    ("galall",   "📖", "図鑑コンプリート", "gallery", None),
    ("allparts", "🌈", "全身バランス",   "parts",    len(BODY_MASTERS)),
]
for _part, (_emoji, _color) in BODY_MASTERS.items():     # 部位マスターを、同じ形で勲章の一覧の後ろに足す
    ACHIEVEMENTS.append((f"master_{_part}", _emoji, f"{_part}マスター", f"part:{_part}", BODY_MASTER_COUNT))
# ロールにもなる勲章: {キー: (ロール名, 色)}
BADGE_ROLES = {f"master_{part}": (f"{emoji} {part}マスター", color) for part, (emoji, color) in BODY_MASTERS.items()}
# 判定する数字ごとの {見出し, 説明の言い方, 単位}
METRIC_INFO = {
    "streak":   ("🔥 連続記録",   "連続",           "日"),
    "gym_days": ("🏃 ジム通い",   "通算",           "日"),
    "pr":       ("📈 自己ベスト", "自己ベスト更新", "回"),
    "records":  ("🧱 記録の数",   "累計記録",       "件"),
    "variety":  ("🎯 バラエティ", "種目の種類",     "種類"),
    "gallery":  ("🖼️ 図鑑",       "図鑑の発見",     "枚"),
    "parts":    ("🌈 全身",       "記録した部位",   "部位"),
}
#-----------------------------------------------------------------------------------------------------

# #インテント:イベントを受信(メッセージ送信、メンバーの入退出、リアクション等) 今回は送信のみ＝default
intents = discord.Intents.default()
intents.message_content = True #メッセの中身を読める
client = discord.Client(intents = intents) #BOT本体のobj


#[M3-1]筋トレ記録から連続日時をカウント(継続日数用)
#連続記録日数。筋トレは毎日はできないので、「プランが登録されている曜日」だけを数える対象にする
#  プランが無い曜日(オフの日)は、記録が無くても連続を切らない(スキップして、その前の日を見る)
def get_streak_days(user_id):
    plan_weekdays = set(db.get_plan_weekdays(user_id))
    if not plan_weekdays:      # プランを1つも登録していない人は、数える対象の曜日が無いので0
        return 0
    streak = 0
    check_date = datetime.now()
    while True:
        if check_date.weekday() in plan_weekdays:   # プランがある曜日だけ判定する。無い曜日は素通り(数えも、切りもしない)
            date_str = check_date.strftime("%Y-%m-%d")
            rows = db.get_today_kintore(user_id, date_str)
            if not rows:
                break          # プランがある日に記録が無かったら、そこで連続が途切れる
            streak += 1
        check_date = check_date - timedelta(days=1)  # 1日前にさかのぼる
    return streak

#=========================================================================================================

#[X0]レベルの計算。そのレベルになるのに必要な「累計XP」= 50 × Lv × (Lv-1)  (Lv1=0 / Lv2=100 / Lv3=300 / Lv5=1000 / Lv10=4500)
#  後ろのレベルほど、次に上がるまでに必要なXPが増えていく
def xp_for_level(level):
    return 50 * level * (level - 1)

def level_from_xp(xp):
    level = 1
    while xp >= xp_for_level(level + 1):    # 次のレベルに必要なXPに届いている間、レベルを上げ続ける
        level += 1
    return level

#今のレベルでもらえる一番上の称号を返す。まだ1つももらえていなければ None
def badge_for_level(level):
    best = None
    for badge in BADGES:                    # 必要なレベルの低い順に並んでいるので、最後に条件を満たしたものが「一番上」
        if level >= badge[0]:
            best = badge
    return best

#「🎖️ Lv.4  ▰▰▰▱▱▱▱▱▱▱  150/300XP」のような1行(バーは今のレベルの中での進み具合)
def level_line(xp):
    lv = level_from_xp(xp)
    base, nxt = xp_for_level(lv), xp_for_level(lv + 1)
    filled = int(10 * (xp - base) / (nxt - base))
    return f"🎖️ Lv.{lv}  {'▰' * filled}{'▱' * (10 - filled)}  {xp - base}/{nxt - base}XP"

#過去の記録ぶんの経験値を、最初に1回だけ付ける(経験値の機能を入れる前に記録した分も無駄にしないため)
#  経験値の履歴が1行も無い人だけが対象。必ず「新しい記録を保存する前」に呼ぶ(呼ぶのが後だと、新しい記録が二重に数えられる)
def ensure_xp_backfill(user_id):
    if db.count_xp_entries(user_id) > 0:
        return
    count, days = db.get_record_stats(user_id)
    amount = count * XP_PER_EXERCISE + days * XP_DAILY_BONUS
    if amount > 0:
        db.add_xp(user_id, amount, f"これまでの記録ぶん（{count}種目・{days}日）", str(datetime.now()))

#[X1]レベルに合わせて、称号ロール(名前の色が変わるロール)を付け替える
#  member = そのサーバーでのメンバー / level = 今のレベル
#  戻り値: "ok"=成功 / "no_permission"=Botに「ロールの管理」権限が無い / "error"=失敗 / None=サーバーの外(DMなど)で何もしなかった
#  ※ロールのアイコン(名前の横の絵)は、サーバーのブーストがレベル2以上でないと使えないので、名前に絵文字を入れたロールにしている
async def sync_level_role(member, level):
    guild = getattr(member, "guild", None)
    if guild is None:
        return None
    if not guild.me.guild_permissions.manage_roles:
        return "no_permission"
    badge = badge_for_level(level)
    ours = {f"{emoji} {name}" for lv, emoji, name, color in BADGES}   # このBotが管理するロール名の集まり(set)
    try:
        wanted = None                                              # 今のレベルで付けたいロール
        if badge:
            lv, emoji, name, color = badge
            role_name = f"{emoji} {name}"
            wanted = discord.utils.get(guild.roles, name=role_name)   # 既にあるロールを名前で探す
            if wanted is None:                                        # 無ければ作る(hoist=True: メンバー一覧で、このロールの見出しの下にまとめて表示する)
                wanted = await guild.create_role(name=role_name, colour=discord.Colour(color), hoist=True, reason="レベルの称号ロール")
        to_remove = [r for r in member.roles if r.name in ours and r != wanted]   # 他の称号ロールが付いていたら外す(付け替え)
        if to_remove:
            await member.remove_roles(*to_remove, reason="称号の更新")
        if wanted is not None and wanted not in member.roles:
            await member.add_roles(wanted, reason="レベルの称号")
        if wanted is not None:
            await raise_role_below_bot(guild, wanted)    # 名前の色が「称号」の色になるよう、ロールを上の方へ置く
    except discord.HTTPException as e:       # Forbidden(権限・ロールの上下関係)なども、HTTPException の仲間
        print(f"[role] ERROR: {e!r}", flush=True)
        return "error"
    return "ok"

#[X1b]レベルに応じて「絵文字解放」ロールを付け外しし、カスタム絵文字の使用ロールにも反映する
#  member = そのサーバーでのメンバー / level = 今のレベル
#  戻り値: "ok" / "no_permission"(ロール権限が無い) / "error" / None(サーバーの外)
EMOJI_UNLOCK_ROLE_NAME = "絵文字解放"
EMOJI_UNLOCK_LEVEL = 5          # このレベルに到達したら解放
EMOJI_UNLOCK_EMOJI_NAME = "saki1"   # 解放するカスタム絵文字の名前(サーバーにアップロード済みのもの)

async def sync_emoji_unlock_role(member, level):
    guild = getattr(member, "guild", None)
    if guild is None:
        return None
    if not guild.me.guild_permissions.manage_roles:
        return "no_permission"
    try:
        role = discord.utils.get(guild.roles, name=EMOJI_UNLOCK_ROLE_NAME)   # 既にあるロールを名前で探す
        if role is None:                                                     # 無ければ作る
            role = await guild.create_role(name=EMOJI_UNLOCK_ROLE_NAME, reason="絵文字解放ロール")
        unlocked = level >= EMOJI_UNLOCK_LEVEL
        if unlocked and role not in member.roles:
            await member.add_roles(role, reason="レベル到達で絵文字解放")
        elif not unlocked and role in member.roles:
            await member.remove_roles(role, reason="レベル不足で絵文字を再ロック")
        # カスタム絵文字の「使えるロール」に、このロールを設定しておく(絵文字ごとに1回設定すれば以後は自動)
        if guild.me.guild_permissions.manage_emojis_and_stickers:
            emoji = discord.utils.get(guild.emojis, name=EMOJI_UNLOCK_EMOJI_NAME)
            if emoji is not None and role not in emoji.roles:
                await emoji.edit(roles=[role], reason="絵文字解放ロールに紐づけ")
    except discord.HTTPException as e:
        print(f"[emoji-unlock] ERROR: {e!r}", flush=True)
        return "error"
    return "ok"

#[X2]ロールをBotのロールのすぐ下まで持ち上げる
#  名前の色は「一番上にあるロール」の色になる。新しく作ったロールは一番下に置かれるので、そのままだと後から作った称号の色が、
#  先に作った部位マスターの色に負けてしまう。称号ロールを上に置いておくことで、称号の色が名前に出るようにしている
#  失敗しても(位置が変えられなくても)称号そのものは付いているので、ログだけ残して先へ進む
async def raise_role_below_bot(guild, role):
    top = guild.me.top_role.position - 1        # Botのロールのすぐ下の位置(Botは自分より上のロールは動かせない)
    if top < 1 or role.position >= top:
        return
    try:
        await role.edit(position=top, reason="称号ロールを上に置く")
    except discord.HTTPException as e:
        print(f"[role] position ERROR: {e!r}", flush=True)

#[B0]勲章(実績)
#  compute_metrics: 勲章の判定に使う数字を、DBの記録から数え直す(数字を別に保存しないので、ズレない)
def compute_metrics(user_id):
    dates = db.get_gym_dates(user_id)          # 記録した日の一覧(古い順)
    best = run = 0                             # best = 最長の連続日数 / run = 今数えている連続日数
    prev = None
    for d in dates:
        day = datetime.strptime(d, "%Y-%m-%d").date()
        run = run + 1 if (prev is not None and (day - prev).days == 1) else 1     # 前の記録日の翌日なら連続、そうでなければ数え直し
        best = max(best, run)
        prev = day
    growth = db.get_growth_data(user_id)       # {種目: [(日付, その日の最大重量), ...]}
    pr = 0                                     # 自己ベストを更新した回数(種目ごとに、それまでの最高を超えた日を数える。初記録は数えない)
    for days in growth.values():
        top = None
        for d, weight in days:
            if top is not None and weight > top:
                pr += 1
            top = weight if top is None else max(top, weight)
    counts = db.get_body_part_counts(user_id)
    record_count, _ = db.get_record_stats(user_id)
    metrics = {"streak": best, "gym_days": len(dates), "pr": pr, "records": record_count, "variety": len(growth),
               "gallery": len(db.get_imgText(user_id)), "parts": sum(1 for part in BODY_MASTERS if counts.get(part, 0) > 0)}
    for part in BODY_MASTERS:
        metrics[f"part:{part}"] = counts.get(part, 0)
    return metrics

def achievement_goal(target):
    return target if target is not None else max(1, len(glob.glob("images/*")))   # None = 図鑑の画像の総数

#  メトリクスの種類から (見出し, 説明の言い方, 単位) を返す。"part:胸" のような部位マスター用の指定にも対応
def metric_info(metric):
    if metric.startswith("part:"):
        return "💪 部位マスター（ロールももらえる）", f"{metric[5:]}の記録", "回"
    return METRIC_INFO[metric]

#  条件を満たした勲章を獲得済みにして、「今回はじめて獲得したもの」のリストを返す(何度呼んでも、同じ勲章を二重に獲得しない)
#  戻り値: (今回獲得した勲章のリスト, 数字の辞書, 獲得済みのキーの集合)
def check_achievements(user_id):
    metrics = compute_metrics(user_id)
    earned = set(db.get_earned_badges(user_id))
    new = []
    for ach in ACHIEVEMENTS:
        key, emoji, name, metric, target = ach
        if key not in earned and metrics[metric] >= achievement_goal(target):
            db.add_earned_badge(user_id, key, str(datetime.now()))
            earned.add(key)
            new.append(ach)
    return new, metrics, earned

def achievement_desc(ach):
    key, emoji, name, metric, target = ach
    section, label, unit = metric_info(metric)
    return f"{label}{achievement_goal(target)}{unit}"

#[B1]獲得済みの「ロールになる勲章」を、サーバーのロールとして付ける(部位マスター)
#  戻り値は sync_level_role と同じ: "ok" / "no_permission" / "error" / None(サーバーの外)。付けるものが無ければ何もせず "ok"
async def sync_badge_roles(member, earned_keys):
    guild = getattr(member, "guild", None)
    if guild is None:
        return None
    keys = [k for k in BADGE_ROLES if k in earned_keys]      # 獲得済みで、ロールになる勲章だけ
    if not keys:
        return "ok"
    if not guild.me.guild_permissions.manage_roles:
        return "no_permission"
    try:
        for key in keys:
            role_name, color = BADGE_ROLES[key]
            role = discord.utils.get(guild.roles, name=role_name)
            if role is None:
                role = await guild.create_role(name=role_name, colour=discord.Colour(color), reason="勲章のロール")
            if role not in member.roles:
                await member.add_roles(role, reason="勲章")
    except discord.HTTPException as e:
        print(f"[role] ERROR: {e!r}", flush=True)
        return "error"
    return "ok"

#[G0]1種目ぶんの「今日の成長」の1行を作る。prev = db.get_previous_records の戻り値(記録する前の過去最高・前回)
#  戻り値: (表示する1行, 自己ベストを更新したか)
def describe_growth(exercise, weight, prev):
    fmt = lambda w: f"{w:g}"      # 50.0 → "50" / 57.5 → "57.5" 。:g = 小数点以下が0なら消してくれる書き方
    if prev["max"] is None:       # この種目を記録するのが初めて
        return f"🆕 {exercise} {fmt(weight)}kg  初記録！\n", False
    is_pr = weight > prev["max"]  # 過去最高より重い = 自己ベスト更新(同じ重量はタイ記録。更新には数えない)
    if is_pr:
        # 自己ベスト！ {これまでの最高}→{今回}kg 達成！ の1行だけにする(以前は「変更内容」欄にも同じ内容が別で出て、二重表示になっていた)
        return f"🏆 {exercise} 自己ベスト！ {fmt(prev['max'])}→{fmt(weight)}kg 達成！\n", True
    if prev["last_weight"] is None:   # 今日より前の記録が無い(=今日すでに記録済みで、これは2回目以降)
        diff_text = ""
    else:
        diff = round(weight - prev["last_weight"], 2)
        if diff == 0:
            diff_text = "（前回と同じ）"
        else:
            diff_text = f"（前回{fmt(prev['last_weight'])}kg → {diff:+g}kg）"   # {diff:+g} = 「+2.5」「-2」のように、プラスの時も + を付ける
    return f"・{exercise} {fmt(weight)}kg {diff_text}\n", False

#[M1-1]筋トレ記録完了メッセージ(共通モジュール)
#  member = 記録した人(サーバーのメンバー)。渡すと、レベルに合わせて称号ロールも付け替える
async def shared_kintore(user_id,record_list,member=None):
#記録する前に今日すでに記録済か確認
    today_str = datetime.now().strftime("%Y-%m-%d")
#                    ↓リストをT/Fに変換。中身が1件でもあればT、空ならF
    already_today = bool(db.get_today_kintore(user_id, today_str))
    ensure_xp_backfill(user_id)          # 過去の記録ぶんの経験値(初回だけ)。新しい記録を保存する「前」に行う
#入力 → dbに記録
    cnt= 0
    growth_lines = ""    # 「今日の成長」の文章(1種目1行)
    pr_count = 0         # 自己ベストを更新した種目の数
    for exercise,weight in record_list:
        body_part = EXERCISE_BODY_PART.get(exercise, "その他")
        # 過去最高と前回は、記録する「前」に調べる(記録した後だと、今の重量自身が過去最高になってしまうため)
        prev = db.get_previous_records(user_id, exercise, today_str)
        db.insert_kintore(user_id, body_part, exercise, weight, DEFO_SETS, str(datetime.now()))
        cnt += 1
        line, is_pr = describe_growth(exercise, weight, prev)
        growth_lines += line
        if is_pr:
            pr_count += 1
#画像ランダム送信イベ
    img_f = glob.glob("images/*")
    found_names = {row[0] for row in db.get_imgText(user_id)}    # 発見済みの画像名の集まり(set)
    unfound = [p for p in img_f if os.path.basename(p) not in found_names]
    # 自己ベストを更新した時は、まだ見つけていない画像の中から必ず1枚選ぶ(ご褒美)。未発見が残っていなければ、いつも通りランダム
    reward = pr_count > 0 and len(unfound) > 0
    img_ph = random.choice(unfound) if reward else random.choice(img_f)
    img_Nm = os.path.basename(img_ph)
    if img_Nm not in found_names:
        db.add_imgText(user_id, img_Nm)
        prefix = "🎁 自己ベストのご褒美！" if reward else "🎉"
        img_text = f"{prefix}新しい画像を発見！({len(found_names)+1}/{len(img_f)}コンプリート)\n"
    else:
        img_text = ""

    #継続記録
    streak = get_streak_days(user_id)
    streak_text = f"🔥継続{streak}日目！\n" if streak > 0 else ""
    summary = f"🔥 今日は自己ベスト{pr_count}種目！\n" if pr_count else ""

#経験値(XP): 種目 + 来た日ボーナス(その日の最初の記録) + 自己ベスト + 連続記録ボーナス(その日の最初の記録)
    xp_text = ""
    badge_prefix = ""      # 返信の1行目の頭に付ける、今の称号の絵文字
    if cnt > 0:
        parts = [f"種目{cnt * XP_PER_EXERCISE}"]
        gain = cnt * XP_PER_EXERCISE
        if not already_today:
            parts.append(f"来た日{XP_DAILY_BONUS}")
            gain += XP_DAILY_BONUS
            streak_xp = XP_STREAK_PER_DAY * min(streak, XP_STREAK_MAX_DAYS)
            if streak_xp > 0:
                parts.append(f"連続{streak_xp}")
                gain += streak_xp
        if pr_count > 0:
            parts.append(f"自己ベスト{pr_count * XP_PR_BONUS}")
            gain += pr_count * XP_PR_BONUS
        old_xp = db.get_total_xp(user_id)
        breakdown = "・".join(parts)                  # 例: "種目50・来た日20・自己ベスト30"
        db.add_xp(user_id, gain, breakdown, str(datetime.now()))
        new_xp = old_xp + gain
        old_lv, new_lv = level_from_xp(old_xp), level_from_xp(new_xp)
        xp_text = f"⭐ +{gain}XP（{breakdown}）\n{level_line(new_xp)}\n"
        if new_lv > old_lv:
            xp_text += f"🎉 レベルアップ！ Lv.{old_lv} → Lv.{new_lv}\n"
        old_badge, new_badge = badge_for_level(old_lv), badge_for_level(new_lv)
        if new_badge is not None and new_badge != old_badge:
            xp_text += f"{new_badge[1]} 「{new_badge[2]}」の称号を獲得！\n"
        if new_badge is not None:
            badge_prefix = f"{new_badge[1]} "
        if member is not None:
            result = await sync_level_role(member, new_lv)     # 称号ロールを付け替える(既に合っていれば、何もしない)
            if result == "no_permission" and new_badge is not None and new_badge != old_badge:
                xp_text += "（名前の色の称号ロールを自動で付けるには、Botに「ロールの管理」権限が必要です）\n"
            await sync_emoji_unlock_role(member, new_lv)       # レベルに応じて絵文字解放ロールも更新

#勲章: 今回の記録で条件を満たした勲章があれば知らせる。部位マスターはサーバーのロールも付ける
    badge_text = ""
    if cnt > 0:
        new_badges, _, earned_keys = check_achievements(user_id)
        role_result = await sync_badge_roles(member, earned_keys) if member is not None else None
        if new_badges:
            badge_text = "🏅 勲章を獲得！\n"
            for ach in new_badges[:5]:                 # 一度にたくさん(最初の1回など)獲得しても、返信が長くなりすぎないよう5個まで
                badge_text += f"　{ach[1]} {ach[2]}（{achievement_desc(ach)}）\n"
                if ach[0] in BADGE_ROLES and role_result == "ok":
                    badge_text += f"　　🎭 「{BADGE_ROLES[ach[0]][0]}」ロールを付けました\n"
            if len(new_badges) > 5:
                badge_text += f"　…ほか{len(new_badges) - 5}個（`b` で一覧）\n"
            if role_result == "no_permission" and any(a[0] in BADGE_ROLES for a in new_badges):
                badge_text += "（部位マスターのロールを自動で付けるには、Botに「ロールの管理」権限が必要です）\n"

    text = f"{badge_prefix}{cnt}種目記録しました！お疲れ様でした💪\n\n📈 今日の成長\n{growth_lines}{summary}\n{xp_text}\n{badge_text}\n{img_text}\n{streak_text}"
    return text , img_ph

#=========================================================================================================

#init:初期化（initialize）」の略。最初の設定
#Python上、クラスの中に定義したメソッド(__init__含む)は、「呼び出されたとき、それがどのインスタンスに対する呼び出しなのか」を自動的に最初の引数として受け取る

WEEKDAY_NAMES = ["月","火","水","木","金","土","日"]   # 曜日番号(0=月〜6=日) → 漢字。WEEKDAY_SETの逆向き
WEIGHT_STEP = 1.0    # 「+1.0kg」「-1.0kg」ボタンで増減する重量(kg)

#[C1-0]プランを「・部位 種目 重量kg セット数」の文章にする(k・リマインダー・曜日切替・プラン編集で共通利用)
def make_plan_text(plan_rows):
    text = ""
    for body_part, exercise, weight, sets in plan_rows:
        text += f"・{body_part} {exercise} {weight}kg {sets}セット\n"
    return text

#[C1-3]重量の変更をプランに反映する(「選んだ種目で記録」ボタン と 重量編集フォーム の共通処理)
#  weekday=どの曜日のプランか / old_rows=変更前のプラン[(部位,種目,重量,セット数)] / record_list=[(種目,新しい重量)]
#  戻り値: 「・種目: 50.0kg → 55.0kg」の文章(変更が無ければ空文字)
def save_plan_changes(user_id, weekday, old_rows, record_list):
    old_weights = {}                                  # 変更前の重量を、種目名をキーにした辞書にしておく
    for body_part, exercise, weight, sets in old_rows:
        old_weights[exercise] = weight
    diff_text = ""
    for exercise, weight in record_list:
        old_weight = old_weights.get(exercise)        # プランに無い種目なら None
        if old_weight is not None and old_weight == weight:
            continue                                   # 重量が変わっていない → プランは触らない
        if old_weight is not None:                     # 重量が変わった → 変更内容の文章に追加
            diff_text += f"・{exercise}: {old_weight}kg → {weight}kg\n"
        body_part = EXERCISE_BODY_PART.get(exercise, "その他")
        db.update_weight_all_weekdays(user_id, exercise, weight)                   # その種目が入っている全曜日を更新
        db.upsert_plan(user_id, body_part, exercise, weight, DEFO_SETS, weekday)   # この曜日のプランに無い種目なら追加
    return diff_text

#[C0]自分の操作だけ受け付けるView(他の人が押しても反応しない)。新しく作る画面はこれを継承する
class OwnerView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは他の人の画面です", ephemeral=True)
            return False
        return True

#[C0-1]「本当にこの内容でよろしいですか？」の再確認画面。記録・削除・修正・プラン変更など、実際に保存する直前に必ずこれを挟む
#  on_yes(interaction) / on_no(interaction) = 「はい」「いいえ」を押した時に呼ぶ関数(呼び出し側で用意する)。
#  どちらの関数も、渡された interaction の response を自分で使い切る(そのメッセージを書き換えて、確認画面を閉じる)
#  danger=True にすると「はい」ボタンが赤色になる(削除のような取り消せない操作の時用)
class ConfirmView(OwnerView):
    def __init__(self, user_id, on_yes, on_no, danger=False):
        super().__init__(user_id)
        yes_btn = discord.ui.Button(label="はい", style=discord.ButtonStyle.danger if danger else discord.ButtonStyle.primary, row=0)
        yes_btn.callback = on_yes                # コールバックに、渡された関数をそのまま使う(interactionを1つ受け取る形が同じなので)
        no_btn = discord.ui.Button(label="いいえ", style=discord.ButtonStyle.secondary, row=0)
        no_btn.callback = on_no
        self.add_item(yes_btn)
        self.add_item(no_btn)

#[C1-1]ボタン＋プルダウン作成(継承元:discord.ui.View)
#  画面の並び(row=段):
#    row0: [選んだ種目で記録] [重量を編集して記録] [-2.5kg] [+2.5kg]   ← ボタン4つ
#    row1: 曜日を切り替えるプルダウン (プランが2曜日以上ある時だけ表示)
#    row2: やった種目にチェックを入れるプルダウン (最初は全部チェック済み。やらなかった種目を外す)
#    row3: 重量を調整する種目を選ぶプルダウン (選んでから ±2.5kg ボタンを押す)
class Make_Msg_Btn(discord.ui.View):
    def __init__(self, user_id, plan_rows, weekday):
        super().__init__(timeout=None) # timeout=None => ボタンを押せる時間を無制限に
        #↑super()は「継承元(親クラス)」にアクセス。super().__init__()は「親が持っている、本来の初期化処理を先に実行してね」
        self.user_id = user_id
        self.base_rows = list(plan_rows)   # DBにあるプランそのまま(=変更前の重量)。「何が変わったか」の比較・保存の基準
        self.plan_rows = list(plan_rows)   # 今表示・記録するプラン。±ボタンで重量が変わるのはこちら(list()でコピーを作る)
        self.weekday = weekday             # 今表示している曜日の番号(0=月〜6=日)
        self.chosen = None                 # チェックされた種目名のリスト。None = まだ触っていない(=全種目が対象)
        self.adjust_target = None          # ±ボタンで重量を変える種目名。None = まだ選んでいない
        self.used = False                  # 記録済みか。True になったらボタンを押しても何もしない(連打による二重記録の防止)

        # ---- 種目のチェック用プルダウン(複数選択できる=実質チェックボックス) ----
        # max_values=種目数 にすると、種目数まで同時に選べる
        self.exercise_select = discord.ui.Select(
            placeholder="やった種目にチェック（外すと除外）",
            min_values=1,
            max_values=len(plan_rows),
            options=self._exercise_options(),
            row=2,
        )
        self.exercise_select.callback = self.on_exercise_select   # 選ばれた時に呼ぶ関数を指定
        self.add_item(self.exercise_select)

        # ---- 重量を調整する種目を選ぶプルダウン(1つだけ選ぶ) ----
        self.adjust_select = discord.ui.Select(
            placeholder=f"重量を調整する種目を選ぶ（±{WEIGHT_STEP}kgボタン用）",
            min_values=1, max_values=1,
            options=self._adjust_options(),
            row=3,
        )
        self.adjust_select.callback = self.on_adjust_select
        self.add_item(self.adjust_select)

        # ---- 曜日切り替えプルダウン(プランがある曜日が2つ以上の時だけ) ----
        self.weekday_select = None
        self.registered_weekdays = db.get_plan_weekdays(user_id)   # 例: [1,2,5,6]
        if len(self.registered_weekdays) >= 2:
            self.weekday_select = discord.ui.Select(
                placeholder="他の曜日のプランに切り替え",
                min_values=1, max_values=1,   # 曜日は1つだけ選ぶ
                options=self._weekday_options(),
                row=1,
            )
            self.weekday_select.callback = self.on_weekday_select
            self.add_item(self.weekday_select)

    # 種目プルダウンの選択肢を作る。value(内部の値)は種目名。
    # default=True が「チェック済み」の表示。チェックを外した種目(self.chosen に無い種目)は外れたまま表示する
    def _exercise_options(self):
        return [discord.SelectOption(label=ex, value=ex, default=(self.chosen is None or ex in self.chosen))
                for body_part, ex, weight, sets in self.plan_rows]

    # 重量調整プルダウンの選択肢。ラベルに今の重量を出す(±ボタンで変わるたびに作り直す)
    def _adjust_options(self):
        return [discord.SelectOption(label=f"{ex}（{weight}kg）", value=ex, default=(ex == self.adjust_target))
                for body_part, ex, weight, sets in self.plan_rows]

    # 曜日プルダウンの選択肢を作る。今表示中の曜日に default=True を付ける(選択中の表示になる)
    def _weekday_options(self):
        return [discord.SelectOption(label=f"{WEEKDAY_NAMES[wd]}曜日のプラン", value=str(wd), default=(wd == self.weekday))
                for wd in self.registered_weekdays]

    # 今表示するメッセージの文章
    def plan_text(self):
        return f"{WEEKDAY_NAMES[self.weekday]}曜日のプラン:\n{make_plan_text(self.plan_rows)}"

    # 今、記録の対象になっている行だけを返す(チェックを外した種目は除く)
    def selected_rows(self):
        if self.chosen is None:
            return self.plan_rows
        return [r for r in self.plan_rows if r[1] in self.chosen]   # r[1] = 種目名

    # 種目のチェックが変わった時。選ばれた種目名を覚えるだけ。defer()=「受け取ったよ」を返して画面は変えない
    async def on_exercise_select(self, interaction: discord.Interaction):
        self.chosen = self.exercise_select.values   # 例: ["ロウマシン","懸垂マシン"]
        await interaction.response.defer()

    # 重量を調整する種目が選ばれた時。種目名を覚えるだけ
    async def on_adjust_select(self, interaction: discord.Interaction):
        self.adjust_target = self.adjust_select.values[0]
        await interaction.response.defer()

    # 曜日が切り替えられた時。その曜日のプランに入れ替えて、メッセージごと書き換える
    async def on_weekday_select(self, interaction: discord.Interaction):
        wd = int(self.weekday_select.values[0])       # values は文字列のリスト → 数字に戻す
        rows = db.get_plan(self.user_id, wd)
        if not rows:
            await interaction.response.send_message("その曜日のプランが見つかりません", ephemeral=True)
            return
        self.weekday = wd
        self.base_rows, self.plan_rows = list(rows), list(rows)
        self.chosen, self.adjust_target = None, None       # 切り替えたので、チェックも調整対象もやり直し
        self.exercise_select.options = self._exercise_options()      # 種目プルダウンの中身を入れ替え
        self.exercise_select.max_values = len(rows)
        self.adjust_select.options = self._adjust_options()
        self.weekday_select.options = self._weekday_options()        # 選択中の曜日の表示を更新
        # edit_message = 押されたメッセージの中身(文章とプルダウン)を書き換える
        await interaction.response.edit_message(content=self.plan_text(), view=self)

    # ±ボタンの共通処理。delta = 増減する重量(+2.5 or -2.5)
    async def shift_weight(self, interaction: discord.Interaction, delta):
        if self.used:                       # 記録済みなら何もしない
            await interaction.response.defer()
            return
        if self.adjust_target is None:
            # ephemeral=True = 押した本人にだけ見えるメッセージ(チャンネルには残らない)
            await interaction.response.send_message("先に「重量を調整する種目」を選んでください", ephemeral=True)
            return
        for i, (body_part, exercise, weight, sets) in enumerate(self.plan_rows):
            if exercise == self.adjust_target:
                # round(…, 2) = 小数の誤差を丸める / max(0.0, …) = 0kgより小さくならないようにする
                self.plan_rows[i] = (body_part, exercise, max(0.0, round(weight + delta, 2)), sets)
        self.adjust_select.options = self._adjust_options()      # ラベルの重量表示も更新
        self.exercise_select.options = self._exercise_options()  # edit_messageは画面の部品を全部送り直すので、種目のチェックの表示も今の状態にそろえる(そろえないと、外した種目が全部チェック済みに戻って見える)
        await interaction.response.edit_message(content=self.plan_text(), view=self)

    # 記録が済んだら、ボタンとプルダウンを全部押せなくする(二重記録の防止)
    async def lock(self, message):
        self.used = True
        self.exercise_select.options = self._exercise_options()   # 「チェックを外した種目は外れたまま」の表示にそろえる
        self.adjust_select.options = self._adjust_options()
        for item in self.children:
            item.disabled = True
        if message is not None:
            await message.edit(view=self)

    #confirm → ボタンが押された時の処理。interaction → messageのボタン版(ボタンにあるs情報)
    @discord.ui.button(label="選んだ種目で記録", style=discord.ButtonStyle.primary, row=0)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.used:      # 連打されて2回目以降に来た分は何もしない(確認画面を出している間も含む)
            await interaction.response.defer()
            return
        record_list = []
        for body_part, exercise, weight, sets in self.selected_rows():   # チェックが付いた種目だけ(重量は±ボタンで調整した後の値)
            record_list.append((exercise, weight))
        preview = "\n".join(f"・{exercise} {weight:g}kg" for exercise, weight in record_list)
        orig_message = interaction.message   # 今のk画面のメッセージ(確認では書き換えない。「はい」を押した時に初めて更新する)

        async def on_yes(yi: discord.Interaction):
            await self.lock(orig_message)   # ここで初めてk画面をロックする(確認画面は別メッセージなので、k画面はそれまで触っていない)
            # ±ボタンで変えた重量は、プランにも反映する(全曜日の同じ種目も更新)。self.base_rows = 変更前のプラン
            # ここの変更内容は、shared_kintore側の「📈 今日の成長」に同じ内容がもう出る(自己ベスト！○→○kg達成！など)ので、別枠では表示しない(二重表示防止)
            save_plan_changes(self.user_id, self.weekday, self.base_rows, record_list)
            text, img_ph = await shared_kintore(self.user_id, record_list, member=yi.user)
            await yi.response.edit_message(content="✅ 記録しました", view=None)   # 確認メッセージ(自分にだけ見える)を閉じる
            await yi.followup.send(text, file=discord.File(img_ph))   # ← 本番の返信はこちらで送る(チャンネルに残る)

        async def on_no(ni: discord.Interaction):
            self.used = False        # 確認中に立てていたロックを解除して、選び直せるようにする
            await ni.response.edit_message(content="❌ 取り消しました。何も記録していません", view=None)

        self.used = True             # 確認中も二重に押されないようにしておく(「いいえ」なら on_no で戻す)
        view = ConfirmView(self.user_id, on_yes, on_no)
        await interaction.response.send_message(f"⚠️ 以下の内容で記録します。よろしいですか？\n\n{preview}", view=view, ephemeral=True)

    @discord.ui.button(label="重量を編集して記録", style=discord.ButtonStyle.success, row=0) #style:色
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        # モーダル(入力フォーム)には、チェックが付いた種目だけを渡す。self(このView)も渡して、送信後にロックできるようにする
        modal = WeightModal(self.user_id, self.selected_rows(), self.weekday, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label=f"-{WEIGHT_STEP}kg", style=discord.ButtonStyle.secondary, row=0)
    async def minus(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.shift_weight(interaction, -WEIGHT_STEP)

    @discord.ui.button(label=f"+{WEIGHT_STEP}kg", style=discord.ButtonStyle.secondary, row=0)
    async def plus(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.shift_weight(interaction, WEIGHT_STEP)

#[C1-2]モーダル作成(入力フォーム)(継承元:discord.ui.Modal)
class WeightModal(discord.ui.Modal, title="重量を編集"):
    def __init__(self, user_id, plan_rows, weekday, parent_view=None):
        super().__init__()
        self.user_id = user_id
        self.weekday = weekday             # 編集対象のプランの曜日(選んだ曜日)。新しい種目はこの曜日のプランに追加する
        self.parent_view = parent_view     # ボタンのView。送信後にロックするために持っておく
        # 「変更前」の基準。ボタン画面から開いた時は、±ボタンで調整する前のプラン(DBの内容)と比べる
        self.old_rows = parent_view.base_rows if parent_view is not None else plan_rows
        default_text = "\n".join(f"{exercise} {weight}" for body_part, exercise, weight, sets in plan_rows)
        self.text_input = discord.ui.TextInput(
        label="種目と重量(1行ずつ)",
        style=discord.TextStyle.paragraph,
        default=default_text,)
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.parent_view is not None and self.parent_view.used:   # 既にボタンで記録済みなら、二重記録しない
            await interaction.followup.send("すでに記録済みです")
            return
        lines = self.text_input.value.split("\n")
        record_list = []
        for line in lines:
            parts = line.split()
            if len(parts) != 2:
                continue
            try:
                weight = float(parts[1])
            except ValueError:
                await interaction.followup.send(f"❌「{line}」: 重量は数字で入力してください（例: ベンチプレス 60）")
                continue
            record_list.append((parts[0], weight))
        if not record_list:
            await interaction.followup.send("記録できる種目がありませんでした")
            return
        preview = "\n".join(f"・{exercise} {weight:g}kg" for exercise, weight in record_list)
        orig_message = interaction.message   # 元のk画面のメッセージ(確認では書き換えない。「はい」を押した時に初めて更新する)
        if self.parent_view is not None:
            self.parent_view.used = True     # 確認中も、k画面のボタンから二重に記録されないようにしておく(「いいえ」なら on_no で戻す)

        async def on_yes(yi: discord.Interaction):
            save_plan_changes(self.user_id, self.weekday, self.old_rows, record_list)   # 変更をプランに反映(全曜日)。変更内容は「今日の成長」に出るので、ここでは表示しない(二重表示防止)
            if self.parent_view is not None:
                await self.parent_view.lock(orig_message)   # ここで初めてk画面をロックする
            text, img_ph = await shared_kintore(self.user_id, record_list, member=yi.user)
            await yi.response.edit_message(content="✅ 記録しました", view=None)   # 確認メッセージ(自分にだけ見える)を閉じる
            await yi.followup.send(text, file=discord.File(img_ph))   # ← 本番の返信はこちらで送る(チャンネルに残る)

        async def on_no(ni: discord.Interaction):
            if self.parent_view is not None:
                self.parent_view.used = False
            await ni.response.edit_message(content="❌ 取り消しました。何も記録していません", view=None)

        view = ConfirmView(self.user_id, on_yes, on_no)
        await interaction.followup.send(f"⚠️ 以下の内容で記録します。よろしいですか？\n\n{preview}", view=view, ephemeral=True)

#[C2]今日の記録の削除・修正UI  (コマンド: d または 削除)
#  ・今日の記録を一覧にして、チェックを入れた記録だけを「削除」または「重量を修正」できる
#  ・件数で消す方式より、消す記録を目で見て選べるので安全
class RecordManageView(OwnerView):
    def __init__(self, user_id):
        super().__init__(user_id)
        self.records = []    # 今日の記録 [(id, 部位, 種目, 重量, 日時), ...]
        self.chosen = []     # チェックされた記録のid(文字列)のリスト
        self.reload()

    # DBから今日の記録を読み直して、プルダウンとボタンを作り直す(削除・修正のたびに呼ぶ)
    def reload(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.records = db.get_records_with_id(self.user_id, today_str)[-25:]   # プルダウンは25個までなので、多い時は新しい25件
        self.chosen = []
        self.clear_items()        # 前の部品を全部外す(作り直すため)
        if not self.records:      # 記録が無ければ、部品は無し
            return
        self.record_select = discord.ui.Select(
            placeholder="削除・修正する記録にチェック",
            min_values=0,                       # 0 = 何もチェックしない状態も許す
            max_values=len(self.records),
            options=[discord.SelectOption(label=f"{ex} {weight}kg", description=created_at[11:16], value=str(rid))
                     for rid, body_part, ex, weight, created_at in self.records],   # created_at[11:16] = 「HH:MM」の部分
            row=0,
        )
        self.record_select.callback = self.on_select
        self.add_item(self.record_select)
        delete_btn = discord.ui.Button(label="選んだ記録を削除", style=discord.ButtonStyle.danger, row=1)
        delete_btn.callback = self.on_delete
        self.add_item(delete_btn)
        edit_btn = discord.ui.Button(label="選んだ記録の重量を修正", style=discord.ButtonStyle.success, row=1)
        edit_btn.callback = self.on_edit
        self.add_item(edit_btn)

    # 画面の文章
    def text(self):
        if not self.records:
            return "📝 今日の記録はまだありません"
        lines = ""
        for n, (rid, body_part, ex, weight, created_at) in enumerate(self.records, start=1):
            lines += f"{n}. {ex} {weight}kg ({created_at[11:16]})\n"
        return f"📝 今日の記録 ({len(self.records)}件)\n{lines}\n記録にチェックを入れて、下のボタンで削除・修正できます"

    # チェックが変わった時。選ばれた記録のidを覚えるだけ
    async def on_select(self, interaction: discord.Interaction):
        self.chosen = list(self.record_select.values)
        await interaction.response.defer()

    async def on_delete(self, interaction: discord.Interaction):
        if not self.chosen:
            await interaction.response.send_message("削除する記録にチェックを入れてください", ephemeral=True)
            return
        ids = [int(x) for x in self.chosen]              # 文字列のidを数字に戻す
        targets = [r for r in self.records if r[0] in ids]
        preview = "\n".join(f"・{ex} {weight}kg（{created_at[11:16]}）" for rid, body_part, ex, weight, created_at in targets)
        orig_message = interaction.message   # 元の一覧のメッセージ(確認では書き換えない。「はい」を押した時に初めて更新する)

        async def on_yes(yi: discord.Interaction):
            n = db.delete_records_by_ids(self.user_id, ids)
            self.reload()                                    # 削除後の最新の一覧に作り直す
            await orig_message.edit(content=self.text(), view=self)   # 元の一覧を更新する
            await yi.response.edit_message(content=f"✅ {n}件削除しました", view=None)   # 確認メッセージ(自分にだけ見える)を閉じる

        async def on_no(ni: discord.Interaction):
            await ni.response.edit_message(content="❌ 取り消しました。何も削除していません", view=None)

        view = ConfirmView(self.user_id, on_yes, on_no, danger=True)
        await interaction.response.send_message(f"⚠️ 以下の記録を削除します。よろしいですか？\n\n{preview}", view=view, ephemeral=True)

    async def on_edit(self, interaction: discord.Interaction):
        if not self.chosen:
            await interaction.response.send_message("修正する記録にチェックを入れてください", ephemeral=True)
            return
        chosen_records = [r for r in self.records if str(r[0]) in self.chosen]   # r[0] = id
        await interaction.response.send_modal(RecordEditModal(self.user_id, chosen_records, self))

#[C2-2]記録の重量を修正するフォーム。選んだ記録が1行ずつ並ぶので、重量の数字だけ書き換える
class RecordEditModal(discord.ui.Modal, title="記録の重量を修正"):
    def __init__(self, user_id, records, parent_view):
        super().__init__()
        self.user_id = user_id
        self.records = records
        self.parent_view = parent_view
        self.text_input = discord.ui.TextInput(
            label="重量だけ変更できます（行の順番は変えない）",
            style=discord.TextStyle.paragraph,
            default="\n".join(f"{ex} {weight}" for rid, body_part, ex, weight, created_at in records),
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        lines = [l for l in self.text_input.value.split("\n") if l.strip()]   # 空行は無視
        if len(lines) != len(self.records):     # 行数が合わないと、どの記録の重量か分からないので、何もせず知らせる
            await interaction.response.send_message(f"行数が違います（{len(self.records)}行で入力してください）。もう一度やり直してください", ephemeral=True)
            return
        new_weights = []
        for line in lines:
            try:
                new_weights.append(float(line.split()[-1]))     # 各行の一番右側の数字を重量として読む
            except ValueError:
                await interaction.response.send_message(f"❌「{line}」: 重量は数字で入力してください。何も修正していません", ephemeral=True)
                return                                          # 1行でも読めなければ、全部やめる(一部だけ修正された状態にしない)
        preview = "\n".join(f"・{ex} {old_weight}kg → {new_weight:g}kg" for (rid, body_part, ex, old_weight, created_at), new_weight in zip(self.records, new_weights))
        orig_message = interaction.message   # 元の一覧のメッセージ(確認では書き換えない。「はい」を押した時に初めて更新する)

        async def on_yes(yi: discord.Interaction):
            for record, weight in zip(self.records, new_weights):   # zip = 2つのリストを同じ順番で1つずつ組にする
                db.update_record_weight(self.user_id, record[0], weight)
            self.parent_view.reload()
            await orig_message.edit(content=self.parent_view.text(), view=self.parent_view)   # 元の一覧を更新する
            await yi.response.edit_message(content=f"✅ {len(new_weights)}件の重量を修正しました", view=None)   # 確認メッセージ(自分にだけ見える)を閉じる

        async def on_no(ni: discord.Interaction):
            await ni.response.edit_message(content="❌ 取り消しました。何も修正していません", view=None)

        view = ConfirmView(self.user_id, on_yes, on_no)
        await interaction.response.send_message(f"⚠️ 以下のとおり修正します。よろしいですか？\n\n{preview}", view=view, ephemeral=True)

#[C3]プラン編集UI  (コマンド: p だけを送る)   ※ p火 のように曜日を付けて送るのは、今まで通りの文字入力での登録
#  ・曜日をメニューで選び、その曜日のプランの種目を「追加・重量の上書き」「削除」できる
class PlanEditView(OwnerView):
    def __init__(self, user_id, weekday):
        super().__init__(user_id)
        self.weekday = weekday    # 今編集している曜日(0=月〜6=日)
        self.rows = []
        self.chosen = []          # 削除する種目にチェックされた種目名
        self.reload()

    # DBから最新のプランを読んで、部品を作り直す。weekday を渡すと、編集する曜日を切り替える
    def reload(self, weekday=None):
        if weekday is not None:
            self.weekday = weekday
        self.rows = db.get_plan(self.user_id, self.weekday)
        self.chosen = []
        self.clear_items()
        counts = db.get_plan_counts(self.user_id)   # {曜日番号: 種目数}
        self.weekday_select = discord.ui.Select(
            placeholder="編集する曜日を選ぶ",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=f"{WEEKDAY_NAMES[wd]}曜日（{counts.get(wd, 0)}種目）", value=str(wd), default=(wd == self.weekday))
                     for wd in range(7)],
            row=0,
        )
        self.weekday_select.callback = self.on_weekday
        self.add_item(self.weekday_select)
        add_btn = discord.ui.Button(label="種目を追加・重量を上書き", style=discord.ButtonStyle.success, row=2)
        add_btn.callback = self.on_add
        if self.rows:     # プランがある曜日だけ「削除」の部品を出す
            self.delete_select = discord.ui.Select(
                placeholder="削除する種目にチェック",
                min_values=0, max_values=len(self.rows),
                options=[discord.SelectOption(label=ex, description=f"{weight}kg", value=ex) for body_part, ex, weight, sets in self.rows],
                row=1,
            )
            self.delete_select.callback = self.on_delete_select
            self.add_item(self.delete_select)
            self.add_item(add_btn)
            delete_btn = discord.ui.Button(label="チェックした種目を削除", style=discord.ButtonStyle.danger, row=2)
            delete_btn.callback = self.on_delete
            self.add_item(delete_btn)
        else:
            self.add_item(add_btn)

    def text(self):
        body = make_plan_text(self.rows) if self.rows else "（まだ登録がありません）\n"
        return f"📋 {WEEKDAY_NAMES[self.weekday]}曜日のプラン\n{body}"

    async def on_weekday(self, interaction: discord.Interaction):
        self.reload(int(self.weekday_select.values[0]))    # 選ばれた曜日に切り替えて、部品を作り直す
        await interaction.response.edit_message(content=self.text(), view=self)

    async def on_delete_select(self, interaction: discord.Interaction):
        self.chosen = list(self.delete_select.values)
        await interaction.response.defer()

    async def on_delete(self, interaction: discord.Interaction):
        if not self.chosen:
            await interaction.response.send_message("削除する種目にチェックを入れてください", ephemeral=True)
            return
        preview = "\n".join(f"・{ex}" for ex in self.chosen)
        orig_message = interaction.message   # 元のプラン画面のメッセージ(確認では書き換えない。「はい」を押した時に初めて更新する)

        async def on_yes(yi: discord.Interaction):
            n = db.delete_plan_exercises(self.user_id, self.weekday, self.chosen)
            self.reload()
            await orig_message.edit(content=self.text(), view=self)   # 元のプラン画面を更新する
            await yi.response.edit_message(content=f"✅ {n}種目をプランから削除しました", view=None)   # 確認メッセージ(自分にだけ見える)を閉じる

        async def on_no(ni: discord.Interaction):
            await ni.response.edit_message(content="❌ 取り消しました。何も削除していません", view=None)

        view = ConfirmView(self.user_id, on_yes, on_no, danger=True)
        await interaction.response.send_message(f"⚠️ 以下の種目をプランから削除します。よろしいですか？\n\n{preview}", view=view, ephemeral=True)

    async def on_add(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PlanAddModal(self.user_id, self.weekday, self))

#[C3-2]プランに種目を追加する(または重量を上書きする)フォーム
#  「対象の曜日」欄に 火土 のように書くと、複数の曜日にまとめて登録できる(同じ種目を複数の曜日に入れる時に便利)
class PlanAddModal(discord.ui.Modal, title="プランに種目を追加・上書き"):
    def __init__(self, user_id, weekday, parent_view):
        super().__init__()
        self.user_id = user_id
        self.parent_view = parent_view
        self.weekday_input = discord.ui.TextInput(
            label="対象の曜日（複数可。例: 火土）",
            default=WEEKDAY_NAMES[weekday],      # 最初は、今開いている曜日が入っている
            max_length=7,                        # 7文字まで(月〜日の全部)
        )
        self.add_item(self.weekday_input)
        self.text_input = discord.ui.TextInput(
            label="種目と重量（1行ずつ）",
            style=discord.TextStyle.paragraph,
            placeholder="例:\nロウマシン 50\n懸垂マシン 14",    # 何も入力していない時に薄く表示される見本
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        # ---- 曜日欄を読む: 1文字ずつ曜日番号に直す(同じ曜日を2回書いても1回だけ) ----
        weekdays = []
        for ch in self.weekday_input.value:
            if ch.isspace():
                continue
            wd = WEEKDAY_SET.get(ch)
            if wd is None:
                await interaction.response.send_message(f"曜日の指定が正しくありません: 「{ch}」（例: 火土）。何も登録していません", ephemeral=True)
                return
            if wd not in weekdays:
                weekdays.append(wd)
        if not weekdays:
            await interaction.response.send_message("対象の曜日を入力してください（例: 火土）", ephemeral=True)
            return
        # ---- 種目と重量を読む(この時点ではDBに書き込まない。確認が「はい」になってから書き込む) ----
        to_add, errors = [], ""      # to_add = [(種目, 重量, 部位), ...]
        for line in self.text_input.value.split("\n"):
            parts = line.split()
            if not parts:
                continue                                       # 空行は無視
            if len(parts) != 2:
                errors += f"❌「{line}」: 「種目 重量」の形で入力してください\n"
                continue
            try:
                weight = float(parts[1])
            except ValueError:
                errors += f"❌「{line}」: 重量は数字で入力してください\n"
                continue
            to_add.append((parts[0], weight, EXERCISE_BODY_PART.get(parts[0], "その他")))
        names = "・".join(WEEKDAY_NAMES[wd] for wd in weekdays)   # 例: "火・土"
        if not to_add:      # 登録できる行が無ければ、確認するまでもないのでそのままエラーだけ表示
            await interaction.response.edit_message(content=f"{errors}\n{self.parent_view.text()}", view=self.parent_view)
            return
        preview = "\n".join(f"・{ex} {weight:g}kg" for ex, weight, body_part in to_add)
        orig_message = interaction.message   # 元のプラン画面のメッセージ(確認では書き換えない。「はい」を押した時に初めて更新する)

        async def on_yes(yi: discord.Interaction):
            for ex, weight, body_part in to_add:
                for wd in weekdays:
                    # 同じ曜日・同じ種目があれば重量を上書き、無ければ追加。指定した曜日だけに反映する(他の曜日は変えない)
                    db.upsert_plan(self.user_id, body_part, ex, weight, DEFO_SETS, wd)
            self.parent_view.reload()
            await orig_message.edit(content=f"{errors}\n{self.parent_view.text()}", view=self.parent_view)   # 元のプラン画面を更新する
            await yi.response.edit_message(content=f"✅ {len(to_add)}種目を{names}曜日のプランに追加・更新しました", view=None)   # 確認メッセージ(自分にだけ見える)を閉じる

        async def on_no(ni: discord.Interaction):
            await ni.response.edit_message(content="❌ 取り消しました。何も追加していません", view=None)

        view = ConfirmView(self.user_id, on_yes, on_no)
        await interaction.response.send_message(f"⚠️ 以下を{names}曜日のプランに追加・更新します。よろしいですか？\n\n{preview}{errors}", view=view, ephemeral=True)

#[C4]画面を最初に送る(コマンドから呼ばれる)
async def send_record_manager(message):
    view = RecordManageView(message.author.id)
    kwargs = {"view": view} if view.children else {}     # 記録が無い時は部品が無いので、viewは付けない
    await message.channel.send(view.text(), **kwargs)

async def send_plan_editor(message, weekday=None, note=""):
    if weekday is None:
        weekday = datetime.now().weekday()          # 指定が無ければ今日の曜日
    view = PlanEditView(message.author.id, weekday)
    await message.channel.send(note + view.text(), view=view)

#=========================================================================================================
#[G1]成長ダッシュボード  (コマンド: g または 成長)
#  全種目の「重量の推移」を、種目ごとのカード(小さなグラフ)にして、1枚の画像に並べる
#   ・カード右上: 「最初の重量 → 今の重量 (増減)」  緑=増えた / 灰色=同じ / 赤=減った
#   ・青い折れ線: その日の最大重量の推移   ・金色の点: 今の記録が自己ベスト
MAX_CARDS = 12    # 1枚の画像に載せる種目数の上限(多い時は、記録した日数が多い種目から)

#[G1-1]ダッシュボードの画像を作る。data = db.get_growth_data の戻り値 / 戻り値: 画像(PNG)が入った BytesIO
def make_growth_dashboard(data):
    # 記録した日数が多い順に並べて、上位 MAX_CARDS 種目だけを使う(sorted の key = 並べ替えの物差し / reverse=True = 大きい順)
    names = sorted(data, key=lambda ex: len(data[ex]), reverse=True)[:MAX_CARDS]
    cols = 2
    rows = -(-len(names) // cols)                        # 切り上げ割り算(5種目→3行)
    # Figure(...) = グラフ全体の入れ物。layout="constrained" で、文字が重ならないように自動で余白を調整してくれる
    fig = Figure(figsize=(12, 2.7 * rows), facecolor="#1e1f22", layout="constrained")
    axes = fig.subplots(rows, cols, squeeze=False)       # rows行×cols列のグラフ枠を作る(squeeze=False = 1行でも常に2次元で受け取る)
    for idx, ax in enumerate(axes.flat):                 # axes.flat = 全部の枠を1列に並べて順に取り出す
        ax.set_facecolor("#2b2d31")
        if idx >= len(names):                            # 種目が奇数の時、余った枠は表示しない
            ax.axis("off")
            continue
        ex = names[idx]
        points = data[ex]                                # [(日付, その日の最大重量), ...]
        dates = [datetime.strptime(d, "%Y-%m-%d") for d, w in points]
        weights = [w for d, w in points]
        first, last, best = weights[0], weights[-1], max(weights)
        delta = round(last - first, 2)
        color = "#57f287" if delta > 0 else ("#b5bac1" if delta == 0 else "#ed4245")
        ax.plot(dates, weights, marker="o", color="#7ec8ff", linewidth=2, markersize=5)
        if len(weights) > 1 and last > max(weights[:-1]):   # 今の記録が、それまでの最高を超えている = 自己ベスト
            ax.plot(dates[-1], last, marker="o", color="#ffd166", markersize=11, zorder=5)
        ax.set_title(ex, loc="left", color="#f2f3f5", fontsize=13, fontweight="bold")                         # 左上: 種目名
        sign = f"{delta:+g}" if delta != 0 else "±0"       # 増減の表記。0の時は「+0」ではなく「±0」にする
        ax.set_title(f"{first:g} → {last:g}kg ({sign})", loc="right", color=color, fontsize=12)               # 右上: 最初→今(増減)
        ax.text(0.02, 0.06, f"自己ベスト {best:g}kg ・ {len(points)}日", transform=ax.transAxes, color="#b5bac1", fontsize=9)
        lo, hi = min(weights), max(weights)
        pad = max((hi - lo) * 0.25, 1.5)                 # 上下の余白(値が全部同じでも、線が枠の端に張り付かないように最低1.5)
        ax.set_ylim(lo - pad * 1.8, hi + pad)            # 下側を多めに空ける(左下の文字と線が重ならないように)
        if len(dates) == 1:                              # 記録が1日だけの時は、点が真ん中に来るように横の範囲を広げる
            ax.set_xlim(dates[0] - timedelta(days=3), dates[0] + timedelta(days=3))
        ax.set_xticks([dates[0], dates[-1]] if len(dates) > 1 else [dates[0]])   # 横軸の目盛りは、最初と最後の日付だけ
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.tick_params(colors="#b5bac1", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#3f4147")
        ax.grid(True, color="#3f4147", linewidth=0.5, alpha=0.6)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    buf.seek(0)
    return buf

#[G1-2]gコマンド: 集計して、文章と画像を送る
async def send_growth(message):
    data = db.get_growth_data(message.author.id)
    if not data:
        await message.channel.send("まだ記録がありません。記録がたまると、成長ダッシュボードが見られます")
        return
    days = set()          # 記録した日付の集まり(set=重複なし)。ジムに行った日数になる
    up = []               # 重量が増えた種目 [(増えた量, 種目名, 最初, 今), ...]
    for ex, pts in data.items():
        for d, w in pts:
            days.add(d)
        delta = round(pts[-1][1] - pts[0][1], 2)
        if delta > 0:
            up.append((delta, ex, pts[0][1], pts[-1][1]))
    header = f"📊 成長ダッシュボード\nジム {len(days)}日 ／ 記録した種目 {len(data)}種目"
    if up:
        top = max(up)     # タプルの max は、先頭の要素(増えた量)が一番大きいものを選ぶ
        header += f"\n🔺 重量が上がった種目 {len(up)}種目 ／ 一番の伸び: {top[1]} {top[2]:g}→{top[3]:g}kg ({top[0]:+g})"
    else:
        header += "\nまだ重量の変化はありません。ここからです💪"
    if len(data) > MAX_CARDS:
        header += f"\n（記録した日数が多い上位{MAX_CARDS}種目を表示しています）"
    buf = await asyncio.to_thread(make_growth_dashboard, data)    # グラフ作りは少し重いので、別スレッドで(Botが固まらないように)
    await message.channel.send(header, file=discord.File(buf, filename="growth.png"))

#=========================================================================================================
#[X2]経験値・レベル・称号の確認  (コマンド: x / 経験値 / レベル)
async def send_profile(message):
    uid = message.author.id
    ensure_xp_backfill(uid)
    xp = db.get_total_xp(uid)
    lv = level_from_xp(xp)
    badge = badge_for_level(lv)
    title = f"{badge[1]} {badge[2]}" if badge else "🌱 ビギナー"
    lines = [f"**{title}**", level_line(xp),
             f"⭐ 累計 {xp:,}XP（次のLv.{lv + 1}まであと {xp_for_level(lv + 1) - xp:,}XP）"]    # {xp:,} = 3桁ごとにカンマ(1,020)
    next_badge = next((b for b in BADGES if b[0] > lv), None)     # 次にもらえる称号(まだ届いていない一番近いもの)
    if next_badge:
        lines.append(f"🏅 次の称号: {next_badge[1]} {next_badge[2]}（Lv.{next_badge[0]} まであと{next_badge[0] - lv}レベル）")
    else:
        lines.append("🏅 すべての称号を獲得しました！")
    streak = get_streak_days(uid)
    if streak > 0:
        lines.append(f"🔥 継続{streak}日")
    _, _, earned = check_achievements(uid)
    lines.append(f"🏅 勲章 {sum(1 for a in ACHIEVEMENTS if a[0] in earned)}/{len(ACHIEVEMENTS)}（`b` で一覧）")
    lines.append(f"\n経験値は 種目+{XP_PER_EXERCISE} ／ 来た日+{XP_DAILY_BONUS} ／ 自己ベスト+{XP_PR_BONUS} ／ 連続+{XP_STREAK_PER_DAY}×日数（{XP_STREAK_MAX_DAYS}日まで）で貯まります")
    result = await sync_level_role(message.author, lv)      # 称号ロールを今のレベルに合わせておく(権限を付けた直後の反映にもなる)
    if result == "no_permission" and badge:
        lines.append("※ 名前の色の称号ロールを自動で付けるには、Botに「ロールの管理」権限が必要です")
    await sync_emoji_unlock_role(message.author, lv)         # 絵文字解放ロールも合わせておく
    await message.channel.send("\n".join(lines))

#[B2]勲章コレクションの画面 (コマンド: b または 勲章)
#  獲得済み=✅(名前を太字) / 未獲得=🔒(いまの数字/目標)。今回はじめて獲得したものには🆕を付ける
async def send_badges(message):
    uid = message.author.id
    new, metrics, earned = check_achievements(uid)
    new_keys = {a[0] for a in new}
    result = await sync_badge_roles(message.author, earned)
    sections = {}                                   # {見出し: [1行ずつの文章]} 勲章を種類ごとにまとめる
    for ach in ACHIEVEMENTS:
        key, emoji, name, metric, target = ach
        section = metric_info(metric)[0]
        goal = achievement_goal(target)
        if key in earned:
            mark = "🆕" if key in new_keys else "✅"
            line = f"{mark} {emoji} **{name}**（{achievement_desc(ach)}）"
        else:
            line = f"🔒 {emoji} {name}（{achievement_desc(ach)}）　いま {metrics[metric]}/{goal}"
        sections.setdefault(section, []).append(line)
    have = sum(1 for a in ACHIEVEMENTS if a[0] in earned)
    text = f"**🏅 勲章コレクション　{have}/{len(ACHIEVEMENTS)}**\n"
    for section, lines in sections.items():
        text += f"\n**{section}**\n" + "\n".join(lines) + "\n"
    if result == "no_permission":
        text += "\n※ 部位マスターのロールを自動で付けるには、Botに「ロールの管理」権限が必要です"
    await message.channel.send(text)

#=========================================================================================================
#[L1]ログインボーナス (コマンド: l / ログボ / ログイン)
#  ・1日に LOGIN_PULLS(10)回、ボタンを押せる。押すたびにランダムで報酬(経験値 or 図鑑の画像)
#  ・その日の最初のメッセージで、画面を自動で出す(1日1回)。押した回数はDBに残るので、あとから `l` で続きを押せる
#  ・押した記録は login_pulls テーブル(1回1行)。「今日あと何回か」は、この行数から数える

#経験値を足して、レベルアップしたら「一言」を返す(称号ロールも付け替える)
#  ※ensure_xp_backfill を先に呼ぶのが大事: 記録より先にログインボーナスで経験値が入ると、「経験値の履歴が0行の人だけ過去の記録ぶんを付ける」処理が飛ばされてしまう
async def grant_xp(user_id, gain, reason, member):
    ensure_xp_backfill(user_id)
    old_xp = db.get_total_xp(user_id)
    db.add_xp(user_id, gain, reason, str(datetime.now()))
    old_lv, new_lv = level_from_xp(old_xp), level_from_xp(old_xp + gain)
    if new_lv == old_lv:
        return ""
    note = f"　🎉 Lv.{old_lv}→Lv.{new_lv}"
    old_badge, new_badge = badge_for_level(old_lv), badge_for_level(new_lv)
    if new_badge is not None and new_badge != old_badge:
        note += f" {new_badge[1]}「{new_badge[2]}」獲得！"
    if member is not None:
        await sync_level_role(member, new_lv)
        await sync_emoji_unlock_role(member, new_lv)
    return note

#画面の文章: 残り回数 + これまでに押した結果(1回目から順に)。全部押し終わったら合計
def login_panel_text(user_id, date_str):
    pulls = db.get_login_pulls(user_id, date_str)
    left = LOGIN_PULLS - len(pulls)
    text = f"🎁 **ログインボーナス**　残り {left}/{LOGIN_PULLS}回\n"
    text += "ボタンを押すたびに、ランダムで報酬がもらえます！\n" if left > 0 else "今日の分はぜんぶ使いました。また明日！\n"
    if pulls:
        text += "\n" + "\n".join(f"{n}回目　{t}" for n, kind, xp, t in pulls)
    if left <= 0:
        images = sum(1 for p in pulls if p[1] == "image")
        text += f"\n\n合計 ⭐ +{sum(p[2] for p in pulls)}XP" + (f"・🖼️ 図鑑の画像 {images}枚" if images else "")
    return text

class LoginBonusView(OwnerView):
    def __init__(self, user_id, left):
        super().__init__(user_id)
        button = discord.ui.Button(label=f"🎁 ボタンを押す（残り{left}回）" if left > 0 else "今日はおしまい",
                                   style=discord.ButtonStyle.success, disabled=(left <= 0))
        button.callback = self.pull        # ボタンを押した時に動く関数を、あとから結びつける(デコレータを使わず、部品を自分で作る書き方)
        self.add_item(button)

    async def pull(self, interaction: discord.Interaction):
        await interaction.response.defer()          # 3秒以内に「受け付けた」と返す(称号ロールの付け替えなどで時間がかかる時のため)
        uid = self.user_id
        today = datetime.now().strftime("%Y-%m-%d")
        extra = []                                  # 画面とは別に送る追加メッセージ(図鑑の画像・勲章)
        img_path = None
        pulls = db.get_login_pulls(uid, today)
        if len(pulls) < LOGIN_PULLS:
            n = len(pulls) + 1                      # 今日の何回目か
            weight, kind, xp, label = random.choices(LOGIN_REWARDS, weights=[r[0] for r in LOGIN_REWARDS])[0]   # 重みつきで1つ選ぶ
            if kind == "image":
                found = {row[0] for row in db.get_imgText(uid)}
                all_imgs = sorted(glob.glob("images/*"))
                unfound = [p for p in all_imgs if os.path.basename(p) not in found]
                if unfound:
                    img_path = random.choice(unfound)
                    label = f"🖼️ 図鑑の新しい画像！({len(found) + 1}/{len(all_imgs)})"
                else:                               # 図鑑がコンプリート済み → 代わりに経験値
                    kind, xp = "xp", LOGIN_IMAGE_FALLBACK_XP
                    label = f"🖼️ 図鑑は全部そろっているので ⭐ +{xp}XP"
            # 先に「n回目を押した」と記録する。連打で同じ回が2つ同時に来ても、記録できるのは1つだけ(負けた方は何も起きない)
            if db.add_login_pull(uid, today, n, kind, xp, label):
                try:
                    if img_path:
                        db.add_imgText(uid, os.path.basename(img_path))
                        new_badges, _, _ = check_achievements(uid)      # 図鑑の枚数で獲得できる勲章
                        if new_badges:
                            extra.append("🏅 勲章を獲得！\n" + "\n".join(f"　{a[1]} {a[2]}（{achievement_desc(a)}）" for a in new_badges[:5]))
                    if xp > 0:
                        note = await grant_xp(uid, xp, f"ログインボーナス{n}回目", interaction.user)
                        if note:
                            db.set_login_pull_text(uid, today, n, label + note)
                except Exception as e:                  # 報酬の付与で失敗しても、画面は更新する(何が起きたかはログに残す)
                    print(f"[login] ERROR: {e!r}", flush=True)
        left = LOGIN_PULLS - len(db.get_login_pulls(uid, today))
        await interaction.edit_original_response(content=login_panel_text(uid, today), view=LoginBonusView(uid, left))
        if img_path:
            await interaction.followup.send("🖼️ 図鑑に新しい画像が追加されました！", file=discord.File(img_path))
        for text in extra:
            await interaction.followup.send(text)

async def send_login_panel(channel, user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    left = LOGIN_PULLS - len(db.get_login_pulls(user_id, today))
    await channel.send(login_panel_text(user_id, today), view=LoginBonusView(user_id, left))

#その日の最初のメッセージで、画面を自動で出す(Botや、サーバーの外(DM)のメッセージは対象外)
async def maybe_send_login_panel(message):
    if message.author.bot or message.guild is None:
        return
    uid = message.author.id
    today = datetime.now().strftime("%Y-%m-%d")
    if len(db.get_login_pulls(uid, today)) >= LOGIN_PULLS:      # 今日の分を使い切っていたら、出さない
        return
    if db.claim_login_panel(uid, today):                        # 今日はじめて(=まだ自動で出していない)時だけ True
        await send_login_panel(message.channel, uid)

#=========================================================================================================
#[Z1]画像図鑑  (コマンド: z または 図鑑)
#  ・images フォルダの全画像を、名前順に並べる(番号は固定)
#  ・「発見済み」= 記録した時にもらった画像(DBの img_texts に入っている画像)
#  ・最初は「一覧」を表示: 全画像を1枚の画像にタイル状に並べる(発見済み=サムネイル+緑の番号 / 未発見=暗いモザイク+「?」+灰色の番号)
#  ・下のプルダウンで発見済みの画像を選ぶと、その画像を大きく表示する(「一覧に戻る」ボタンで戻る)
#  ・未発見はモザイクにして、個人の写真の中身が分からないようにしている

#[Z1-0]縮小画像(サムネイル)のキャッシュ
#  42枚(1枚数MB)を毎回読み込むと遅いので、一度縮小したものをメモリに覚えておく
THUMB_W, THUMB_H = 200, 125    # 一覧の1マスの大きさ(px)
_thumb_cache = {}              # {画像のパス: 縮小したPillow画像}

def get_thumb(path):
    if path not in _thumb_cache:          # まだ覚えていない画像だけ、読み込んで縮小する
        with Image.open(path) as im:
            im = im.convert("RGB")
        # マスの縦横比(200:125)にそろえるため、中央を切り抜く(はみ出す左右 or 上下を切り落とす)
        w, h = im.size
        target = THUMB_W / THUMB_H
        if w / h > target:                # 横長すぎる → 左右を切る
            new_w = int(h * target)
            left = (w - new_w) // 2
            im = im.crop((left, 0, left + new_w, h))
        else:                             # 縦長すぎる → 上下を切る
            new_h = int(w / target)
            top = (h - new_h) // 2
            im = im.crop((0, top, w, top + new_h))
        _thumb_cache[path] = im.resize((THUMB_W, THUMB_H))
    return _thumb_cache[path]

#Bot起動時に、裏で全画像の縮小を済ませておく(最初の z を待たせないため)
def warm_zukan_cache():
    try:
        for p in glob.glob("images/*"):
            get_thumb(p)
    except Exception as e:
        print(f"[zukan] cache warm-up error: {e!r}", flush=True)

#[Z1-1]一覧画像(コンタクトシート)を作る。all_images=全画像のパス(名前順) / found=発見済みのファイル名の集合
def make_zukan_sheet(all_images, found):
    cols, gap = 7, 8                                   # 7列で並べる / マスの間のすき間(px)
    rows = -(-len(all_images) // cols)                 # 切り上げ割り算(42枚→6行、43枚→7行)。-(-a // b) は「切り上げ」の定番の書き方
    W = cols * THUMB_W + (cols + 1) * gap
    H = rows * THUMB_H + (rows + 1) * gap
    sheet = Image.new("RGB", (W, H), (32, 32, 36))     # 暗い灰色の背景の画像を作る
    draw = ImageDraw.Draw(sheet)                       # この画像に文字や四角を描くための道具
    font_no = ImageFont.load_default(size=22)          # 番号用の文字(Pillow内蔵のフォント。大きさだけ指定)
    font_q = ImageFont.load_default(size=64)           # 「?」用の大きい文字
    for i, path in enumerate(all_images):
        r, c = divmod(i, cols)                         # divmod(i, 7) = (行, 列)。例: 9枚目(i=8) → 2行目(r=1)の2列目(c=1)
        x = gap + c * (THUMB_W + gap)
        y = gap + r * (THUMB_H + gap)
        is_found = os.path.basename(path) in found
        tile = get_thumb(path)
        if not is_found:                               # 未発見: 10x6px まで縮小 → 拡大(四角いブロック=モザイク)→ 暗くする
            tile = tile.resize((10, 6)).resize((THUMB_W, THUMB_H), Image.Resampling.NEAREST)
            tile = ImageEnhance.Brightness(tile).enhance(0.35)
        sheet.paste(tile, (x, y))
        if not is_found:                               # anchor="mm" = 指定した座標が文字の真ん中(middle-middle)になる
            draw.text((x + THUMB_W // 2, y + THUMB_H // 2), "?", font=font_q, fill=(220, 220, 220), anchor="mm")
        badge = (40, 160, 90) if is_found else (90, 90, 96)   # 番号の札の色: 発見済み=緑 / 未発見=灰色
        draw.rectangle((x, y, x + 44, y + 28), fill=badge)
        draw.text((x + 22, y + 14), f"{i + 1:02d}", font=font_no, fill=(255, 255, 255), anchor="mm")
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf

#[Z1-2]1枚を大きく表示するためのファイルを作る(長辺1024pxに縮小。元は数MBあり、そのまま送ると重い)
def make_zukan_file(path, no):
    with Image.open(path) as im:
        img = im.convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return discord.File(buf, filename=f"zukan_{no:02d}.jpg")   # 番号ごとに名前を変える(画面の古い画像が残らないように)

#[Z1-3]図鑑のメッセージ(継承元:discord.ui.View)
class ZukanView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.all_images = sorted(glob.glob("images/*"))   # 全画像(名前順に固定 → 図鑑番号が変わらない)
        self.found = set()        # 発見済みの画像ファイル名の集まり(set=重複なし・「入っているか」の判定が速い)
        self.mode = "grid"        # "grid"=一覧 / "detail"=1枚を大きく表示
        self.detail_index = 0     # 大きく表示している画像は何番目か(0始まり)

    # 自分の図鑑の操作だけ受け付ける(他の人が押しても反応しない)
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは他の人の図鑑です", ephemeral=True)
            return False
        return True

    # ボタンとプルダウンを、今の状態に合わせて作り直す(発見済みの画像が増えるとプルダウンの中身も変わるため、毎回作り直す)
    def rebuild(self):
        self.clear_items()
        if self.mode == "detail":
            back = discord.ui.Button(label="一覧に戻る", style=discord.ButtonStyle.primary, row=0)
            back.callback = self.on_back
            self.add_item(back)
        # プルダウン1つに入れられる選択肢は最大25個。なので25枚ずつの範囲ごとにプルダウンを作る(42枚なら No.01〜25 と No.26〜42 の2つ)
        row = 1
        total = len(self.all_images)
        for start in range(0, total, 25):
            end = min(start + 25, total)
            options = []
            for i in range(start, end):
                if os.path.basename(self.all_images[i]) in self.found:   # 発見済みの画像だけ選べる
                    options.append(discord.SelectOption(label=f"No.{i + 1:02d}", value=str(i), description="発見済み"))
            if not options:
                continue                                                  # その範囲に発見済みが無ければ、プルダウンは作らない
            select = discord.ui.Select(placeholder=f"No.{start + 1:02d}〜{end:02d} から選んで拡大（{len(options)}枚）",
                                       options=options, row=row)
            select.callback = self.make_select_callback(select)
            self.add_item(select)
            row += 1
            if row > 4:                                                   # 1つのメッセージに置ける段は5つまで(0〜4)
                break

    # プルダウンが選ばれた時の処理を作る。callback には interaction しか渡されないので、
    # 「どのプルダウンか」を関数の中に持たせるために、関数を返す関数にしている(クロージャ)
    def make_select_callback(self, select):
        async def callback(interaction: discord.Interaction):
            self.detail_index = int(select.values[0])   # 選ばれた値(文字列)を数字に戻す
            self.mode = "detail"
            await self.show(interaction)
        return callback

    async def on_back(self, interaction: discord.Interaction):
        self.mode = "grid"
        await self.show(interaction)

    # 今の状態から「文章」と「画像ファイル」を作る。戻り値: (文章, ファイル)
    async def render(self):
        self.found = {row[0] for row in db.get_imgText(self.user_id)}   # 表示のたびにDBから最新の発見状況を読み直す
        total = len(self.all_images)
        found_n = len([p for p in self.all_images if os.path.basename(p) in self.found])
        header = f"📖 画像図鑑  発見 {found_n}/{total} ({found_n * 100 // max(total, 1)}%)"
        self.rebuild()
        if self.mode == "detail":
            self.detail_index %= total
            no = self.detail_index + 1
            # 画像の変換は少し重いので、別スレッドで実行して Bot が固まらないようにする(asyncio.to_thread)
            file = await asyncio.to_thread(make_zukan_file, self.all_images[self.detail_index], no)
            return f"{header}\nNo.{no:02d} ✅ 発見済み", file
        buf = await asyncio.to_thread(make_zukan_sheet, self.all_images, self.found)
        if found_n:
            hint = "下のメニューから選ぶと大きく見られます（一覧の画像をクリックすると拡大できます）"
        else:
            hint = "まだ発見した画像がありません。記録するともらえます！"
        return f"{header}\n{hint}", discord.File(buf, filename=f"zukan_list_{found_n}.jpg")

    # 操作されたら、表示を作り直してメッセージごと書き換える
    async def show(self, interaction: discord.Interaction):
        await interaction.response.defer()   # 画像の作成に3秒以上かかることがあるので、先に「受け取った」を返す(WeightModalと同じ理由)
        content, file = await self.render()
        # attachments=[新しい画像] で、前の画像と入れ替わる
        await interaction.edit_original_response(content=content, attachments=[file], view=self)

#[Z1-4]図鑑を最初に送る(zコマンドから呼ばれる)
async def send_zukan(message):
    view = ZukanView(message.author.id)
    if not view.all_images:
        await message.channel.send("images フォルダに画像がありません")
        return
    content, file = await view.render()
    await message.channel.send(content, file=file, view=view)

#=========================================================================================================
       
#関数（def）:何か待っている間はプログラム全体が完全に止まってしまう
# # [9/20修正]今日記録したか追加のため 削除 => @tasks.loop(time=REM_HOUR) #18時になったら起動

#[M2-2]今日の記録がされていなかったらリマインダー
async def send_reminder():
    today = datetime.now()
    if today.weekday() not in [1,2,5,6]: #月=0 〜 日=6
        return
    today_str = datetime.now().strftime("%Y-%m-%d")
    rows = db.get_today_kintore(MY_USER_ID,today_str)
    if not rows:
        channel = client.get_channel(CH_ID)
        plan_rows = db.get_plan(MY_USER_ID, today.weekday())
        if plan_rows:
            preview = ""
            for body_part, exercise, weight, sets in plan_rows:
                preview += f"・{body_part} {exercise} {weight}kg {sets}セット\n"
            view = Make_Msg_Btn(MY_USER_ID, plan_rows, today.weekday())   # 3つ目 = 今日の曜日番号
            await channel.send(f"<@{MY_USER_ID}>まだ今日の記録がありません！\n{preview}", view=view)
        else:
            await channel.send(f"<@{MY_USER_ID}>まだ今日の記録がありません！筋トレしましょう💪")

# [9/20修正]今日記録したか追加のため 削除　=> @tasks.loop(time=TOMO_HOUR) 
#[M2-3]明日の予定を通知
async def send_tomoPlan():
    #除法あまり利用　(6 + 1) % 7   # → 0  (日曜の次は月曜=0に戻る) → (1 + 1) % 7   # → 2  (火曜の次は水曜)
    tomor_weekday = (datetime.now().weekday() + 1) % 7
    rows = db.get_plan(MY_USER_ID, tomor_weekday)
    if not rows:
        return
    plan_text = f"明日の筋トレ予定💪\n"
    for body_part, exercise, weight, sets in rows: #各パーツを1行ずつ
        plan_text += f"・{body_part} {exercise} {weight}kg {sets}セット\n"
    
    channel = client.get_channel(CH_ID)
    await channel.send(plan_text)

#[M2-4]リマインダー、明日の予定が送られているか判定
@tasks.loop(minutes=10)
async def ck_notified():
    try:
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        # 18時以降　かつ　リマインダーを送っていない
        if now.hour >= REM_HOUR and not db.is_notified("reminder", today_str):
            await send_reminder()
            db.insert_notified("reminder", today_str)   # 「送った」と記録(二重送信防止)
            print(f"[notify] reminder sent {today_str}", flush=True) #成功用ログ

        if now.hour >= TOMO_HOUR and not db.is_notified("plan", today_str):
            await send_tomoPlan()
            db.insert_notified("plan", today_str)
            print(f"[notify] plan checked {today_str}", flush=True) #成功用ログ
    except Exception as e: #例外エラーをログへ
        print(f"[notify] ERROR: {e!r}", flush=True)

#[M2-1]Botがログインに成功した瞬間に、一度だけ実行される処理
@client.event
async def on_ready(): #関数名は固定(Discordがこれを探す)
    print(f"ログイン成功:{client.user}")
    if not ck_notified.is_running(): #.is_running() => そのタスクが今、動いている最中か をT/Fで返す =>スリープごとの再重複を防ぐ
        # ↑discord.pyがDiscordと接続し直し、その新しいセッションが始まるたびにon_readyが呼ばれる。
        ck_notified.start()
    asyncio.create_task(asyncio.to_thread(warm_zukan_cache))   # 図鑑用の縮小画像を裏で準備(既に準備済みなら一瞬で終わる)
    


#[9/20 改修] 今日送ったか判定追加のため削除
#   today_reminder.start() #today_reminder()括弧つけるとすぐ実行してだから注意
#   tomo_plan.start()

#=========================================================================================================

#awaitとasync def :（非同期関数）は「待っている間、他の処理に切り替えられる」という特徴。
#async defで定義した関数（非同期関数）の中で、「時間のかかる処理の完了を待つ」ときに使うキーワードです。
#普通の関数呼び出しと違うのは、awaitで待っている間、プログラム全体は止まらず、他の処理に切り替えられるという点です。
# 例えばawait message.channel.send(...)は「Discordにメッセージを送って、送信が完了するのを待つ」処理ですが、送信中（ネットワーク通信中）
# でも、Bot自体は他のメッセージやイベントに反応し続けられます。

#[M1-2]メッセージ取得
#[H1]ヘルプ(コマンドの使い方一覧)の文章。h / ? / help / ヘルプ だけを送ると表示される
#  f""" ... """ = 複数行のf文字列。{ } の中に変数を入れられるので、設定を変えても説明が自動でそろう
HELP_TEXT = f"""📖 **使い方**

**■ 記録する**
`k` … 今日のプランを表示（ボタンで記録・±{WEIGHT_STEP}kg調整・種目のチェック・曜日の切り替え）
　プランに無い種目は「重量を編集して記録」のフォームに「種目 重量」を書き足すと記録できます（その曜日のプランにも追加されます）

**■ プランを登録・編集する**
`p` … プランの編集画面（曜日を選んで、種目の追加・削除）
　`p火` のように曜日を付けると、その曜日で開きます。「種目を追加」フォームの曜日欄に `火土` と書くと、複数の曜日にまとめて登録できます

**■ 記録を直す**
`d`（または `削除`） … 今日の記録を選んで、削除・重量の修正

**■ 見る**
`z`（または `図鑑`） … 画像図鑑
`g`（または `成長`） … 成長ダッシュボード（全種目の重量の推移を1枚の画像で）
`x`（または `レベル`） … 経験値・レベル・称号の確認
`b`（または `勲章`） … 勲章コレクション（獲得済みと、あといくつで獲得できるか）
`!data種目名` … 重量の推移グラフ（例: `!dataロウマシン`）

**■ ログインボーナス**
`l`（または `ログボ`） … 1日{LOGIN_PULLS}回、ボタンを押してランダムで報酬（経験値・図鑑の画像）。その日の最初のメッセージで自動でも出ます

**■ 自動のお知らせ**
・{REM_HOUR}時以降に、まだ記録が無いジムの日はリマインダー
・{TOMO_HOUR}時以降に、明日のプランをお知らせ

**■ おまけ**
連続で記録した日数が表示されます（プランが登録されている曜日だけを数えます。プランが無い曜日は記録が無くても途切れません）。
自己ベストを更新すると「🏆」が出て、図鑑の**まだ見つけていない画像が必ず1枚**もらえます。
経験値（XP）は 記録・来た日・自己ベスト・連続記録 で貯まり、レベルが上がると称号（🥉🥈🥇💎👑）と、名前の色のロールがもらえます。
連続記録・自己ベスト・図鑑などで**勲章**、各部位（胸・背中・脚・肩）を{BODY_MASTER_COUNT}回記録すると「部位マスター」のロールがもらえます。

`h` または `?` … この説明"""

#⭐️【テスト】②サイコロアニメーション
#  メッセージを短い間隔で書き換えて、回転してるように見せてから結果を確定する
DICE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]   # 1〜6の目のユニコード文字

async def roll_dice(message):
    msg = await message.channel.send("🎲 サイコロを振っています…")
    for _ in range(5):                              # 5回、ランダムな目に書き換えて「回転」演出
        await asyncio.sleep(0.3)
        fake = random.choice(DICE_FACES)
        await msg.edit(content=f"🎲 {fake}")
    await asyncio.sleep(0.3)
    result = random.randint(1, 6)
    await msg.edit(content=f"🎲 出た目: {DICE_FACES[result - 1]}（{result}）")

#⭐️レベルに応じた絵文字解放の一覧表示
#  実際のロール制限(sync_emoji_unlock_role)は一覧からの表示/非表示で反映される。ここではLvに応じて🔒が外れる様子をテキストで見せる
EMOJI_UNLOCKS = [
    (1, "😀", "スマイル"),
    (5, "<:saki1:1552447083292663808>", "ファイア"),
    (5, "💎", "ダイヤ"),
    (10, "👑", "クラウン"),
]

async def send_emoji_unlock_demo(message):
    uid = message.author.id
    ensure_xp_backfill(uid)
    xp = db.get_total_xp(uid)
    lv = level_from_xp(xp)
    lines = [f"あなたは Lv.{lv} です\n"]
    for need_lv, emoji, name in EMOJI_UNLOCKS:
        if lv >= need_lv:
            lines.append(f"{emoji} {name} ── 解放済み(Lv.{need_lv}〜)")
        else:
            lines.append(f"🔒 {name} ── Lv.{need_lv}で解放（あと{need_lv - lv}）")
    await message.channel.send("\n".join(lines))

@client.event
async def on_message(message):
    if message.author == client.user: # Bot自身のメッセージには反応しない（無限ループ防止）
        return
    content_lower = message.content.lower() #コマンド判定用(大文字小文字を区別しない)。実際のデータ取り出しはmessage.contentを使う
    #⭐️---ログインボーナス(その日の最初のメッセージで自動表示。l と打った時は、下で開くので二重に出さない)---
    if content_lower.strip() not in ("l", "ログボ", "ログイン"):
        try:
            await maybe_send_login_panel(message)
        except Exception as e:                  # ログインボーナスで失敗しても、本来のコマンドは動かす
            print(f"[login] panel ERROR: {e!r}", flush=True)
    #⭐️---記録---
    if content_lower.startswith("k"): # startswith:指定した文字から始まっているか判定(先頭!k)
        # 文字での記録(k の次の行に「種目 重量」を書く方式)は廃止した。記録は画面のボタン・フォームから行う。
        # 昔の癖で2行以上で送られた時は、黙って無視せず、説明を添える
        note = "※文字での記録はできなくなりました。下のボタン・フォームから記録してください\n\n" if "\n" in message.content.strip() else ""
        today_weekday = datetime.now().weekday()
        weekday = today_weekday
        plan_rows = db.get_plan(message.author.id, weekday)
        if not plan_rows:
            # 今日のプランが無い日は、プランが登録されている曜日を代わりに表示する(メニューで他の曜日にも切り替えられる)
            weekdays = db.get_plan_weekdays(message.author.id)     # 例: [1,2,5,6]
            if not weekdays:
                await message.channel.send("プランが1つも登録されていません。`p` でプランを登録してください")
                return
            # next(条件に合う最初の要素, 無かった時の値) = 「今日より後の曜日」のうち一番近いもの。無ければ一番若い曜日に戻る
            weekday = next((w for w in weekdays if w > today_weekday), weekdays[0])
            plan_rows = db.get_plan(message.author.id, weekday)
            head = (f"今日（{WEEKDAY_NAMES[today_weekday]}曜日）のプランは未登録です。"
                    f"{WEEKDAY_NAMES[weekday]}曜日のプランを表示しています（メニューで他の曜日にも切り替えられます）\n\n"
                    f"{WEEKDAY_NAMES[weekday]}曜日のプラン:\n")
        else:
            head = "今日のプラン:\n"
        view = Make_Msg_Btn(message.author.id, plan_rows, weekday) # [C1-1] 3つ目 = 表示する曜日番号
        await message.channel.send(f"{note}{head}{make_plan_text(plan_rows)}", view=view)
    #⭐️---画像図鑑---
    elif content_lower.startswith("z") or message.content.startswith("図鑑"):
        await send_zukan(message)
    #⭐️---今日の記録の削除・修正UI---
    elif content_lower.strip() == "d" or message.content.strip() == "削除":   # 「d」または「削除」だけの時(ぴったり一致した時だけ反応する)
        await send_record_manager(message)
    #⭐️---経験値・レベル・称号---
    elif content_lower.strip() in ("x", "経験値", "レベル", "lv"):   # ぴったり一致した時だけ反応する
        await send_profile(message)
    #⭐️---ログインボーナス(今日の続きを押す)---
    elif content_lower.strip() == "l" or message.content.strip() in ("ログボ", "ログイン"):
        db.claim_login_panel(message.author.id, datetime.now().strftime("%Y-%m-%d"))   # 自分で開いたら、今日の自動表示は済みにする(あとで二重に出さない)
        await send_login_panel(message.channel, message.author.id)
    #⭐️---勲章コレクション---
    elif content_lower.strip() == "b" or message.content.strip() == "勲章":   # ぴったり一致した時だけ反応する
        await send_badges(message)
    #⭐️---成長ダッシュボード---
    elif content_lower.strip() == "g" or message.content.strip() == "成長":   # 「g」または「成長」だけの時(ぴったり一致した時だけ反応する)
        await send_growth(message)
    #⭐️---ヘルプ(使い方の一覧)---
    elif content_lower.strip() in ("h", "?", "？", "help", "ヘルプ"):   # in (...) = 「この中のどれかとぴったり一致するか」。普通の文章(hello など)には反応しない
        await message.channel.send(HELP_TEXT)
    #⭐️---(廃止)!delete → 今日の記録の削除は d の画面に移った。昔の癖で送られた時だけ、案内を返す---
    elif content_lower.startswith("!delete"):
        await message.channel.send("`!delete` はなくなりました。`d` で今日の記録を選んで削除できます")

    #⭐️---計画の書き込み---
    elif content_lower.startswith("p"):
        # 文字での登録(p火 の次の行に「種目 重量」を書く方式)は廃止した。プラン編集画面の「種目を追加」フォームから登録する
        first_line = message.content.strip().split("\n")[0]      # 1行目だけ見る 例: "p火"
        day_part = first_line[1:].strip()                        # "p" の後ろの部分 例: "火"
        weekday = datetime.now().weekday()                       # 曜日の指定が無ければ、今日の曜日で開く
        if day_part:
            weekday = WEEKDAY_SET.get(day_part[0])               # 最初の1文字だけを曜日として読む。.get = 無ければ None
            if weekday is None:
                await message.channel.send(f"曜日の指定が正しくありません（例: p火）: 「{day_part[0]}」")
                return
        note = "※文字での登録はできなくなりました。下の「種目を追加」フォームから登録してください\n\n" if "\n" in message.content.strip() else ""
        await send_plan_editor(message, weekday, note)

    #⭐️---グラフの出力---
    elif content_lower.startswith("!data"):
        exercise = message.content[5:] #5文字以降(deleteの後ろ) ※0はじまり
        if exercise == "":
            await message.channel.send("使い方: !data種目名 (例: !dataベンチプレス)")
            return
        rows = db.exercise_history(message.author.id,exercise)
        if not rows:
            await message.channel.send(f"「{exercise}」の記録が見つかりません")
            return
        #日付(date)と重さ(weight)のプロットグラフを作成
        dates,weights = [],[]
        for created_at,weight in rows:
            d = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S.%f") # [%f:マイクロ秒]strptime:文字列をdatetimeObjに変換。
            dates.append(d)
            weights.append(weight)
        #グラフの詳細設定
        plt.plot(dates, weights, marker="o") # o:折れ線グラフ
        plt.title(f"{exercise}の重量推移")
        plt.xlabel("日付")
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        plt.xticks(rotation=45) #X軸をななめ45°
        plt.ylabel("重量(kg)")
        plt.savefig("graph.png") # グラフを画像ファイルで保存
        plt.close() # 描いたグラフを閉じてメモリを解放（Botはずっと動き続けるプログラムなので、閉じ忘れるとメモリが溜まっていく）

        await message.channel.send(file=discord.File("graph.png"))

    #⭐️---【テスト】サイコロ---
    elif content_lower.strip() in ("サイコロ", "dice"):
        await roll_dice(message)

    #⭐️---絵文字解放(レベルに応じて🔒が外れる一覧)---
    elif content_lower.strip() in ("絵文字", "emoji"):
        await send_emoji_unlock_demo(message)

client.run(TOKEN)