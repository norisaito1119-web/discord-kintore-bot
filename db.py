import sqlite3

cone = sqlite3.connect("kintore.db")# ①DBファイルに接続（なければ自動で作られる）
cur = cone.cursor()                 # ②SQLを実行するための「カーソル」

# ③テーブル作成SQL文を実行(kintores:テーブルの宣言名　id~ 自動で連番id)
#REAL型　QLiteの型の1つで、小数を含む数値（浮動小数点数） weightはNULL可
cur.execute("""
    CREATE TABLE IF NOT EXISTS kintores(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    body_part TEXT,
    exercise TEXT,
    weight REAL,
    sets INTEGER,
    created_at TEXT)
""")           
cur.execute("""
    CREATE TABLE IF NOT EXISTS plans(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,body_part TEXT,exercise TEXT,weight INTEGER,sets INTEGER,weekday INTEGER)
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS img_texts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,image TEXT)
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS notified(
    kind TEXT,sent_date TEXT)
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS xp_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, amount INTEGER, reason TEXT, created_at TEXT)
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS badges_earned(
    user_id INTEGER, key TEXT, earned_at TEXT,
    PRIMARY KEY(user_id, key))
""")   # 勲章の獲得記録。PRIMARY KEY(user_id, key) = 同じ人が同じ勲章を2回もらう行は作れない
cur.execute("""
    CREATE TABLE IF NOT EXISTS login_pulls(
    user_id INTEGER, date TEXT, n INTEGER, kind TEXT, xp INTEGER, text TEXT,
    PRIMARY KEY(user_id, date, n))
""")   # ログインボーナスを押した記録(1回押すごとに1行)。n=その日の何回目か。PRIMARY KEY で「同じ回を2回押す」(連打)を防ぐ
cur.execute("""
    CREATE TABLE IF NOT EXISTS login_panels(
    user_id INTEGER, date TEXT,
    PRIMARY KEY(user_id, date))
""")   # 「今日のログインボーナス画面を自動で出した」記録(1日1回だけ出すため)

#[M1-1]kintoresテーブルに新しい行（レコード）を1件追加(INSERT~)　
#?は「値はここに後から渡すよ」というプレースホルダー（空欄・穴）
def insert_kintore(user_id, body_part, exercise, weight, sets, created_at):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()                 
    cur.execute("""
        INSERT INTO kintores(user_id, body_part, exercise, weight, sets, created_at)
        VALUES(?,?,?,?,?,?)
    """,(user_id, body_part, exercise, weight, sets, created_at))
    cone.commit()                    
    cone.close()

#[M1-2]今日付のデータ取得(str_today = "2026-08-19")
def get_today_kintore(user_id,str_today):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()                 
    cur.execute("""
        SELECT body_part, exercise, weight, sets FROM kintores
        WHERE user_id = ? AND  created_at LIKE ?
    """,(user_id,str_today + "%"))
    #↑created_at列は"2026-08-19 22:14:19.123456"
    rows = cur.fetchall() #複数行を取得
    cone.close()
    return rows

# [M1-3]今月、記録があった日(重複なし)(今月何回ジムに行ったか)
# ISTINCT: 結果の重複を除く。
# substr(created_at, 1, 10):1~10文字分取り出す→ 2026-09-06 
def get_gym_month(user_id, year_month):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("""
        SELECT DISTINCT substr(created_at, 1, 10) FROM kintores
        WHERE user_id = ? AND created_at LIKE ?
    """, (user_id, year_month + "%"))
    rows = cur.fetchall()
    cone.close()
    return rows

#[M1-4]部位グラフ用のデータ取得
def exercise_history(user_id,exercise):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()                 
    cur.execute("""
        SELECT created_at,weight FROM kintores
        WHERE user_id = ? AND exercise = ?
        ORDER BY created_at 
    """,(user_id,exercise))
    rows = cur.fetchall()
    cone.close()
    return rows

#[M2-2]曜日にあわせたプランを取得する
def get_plan(user_id,weekday):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()                 
    cur.execute("""
        SELECT body_part, exercise, weight, sets FROM plans
        WHERE user_id = ? AND  weekday = ?
    """,(user_id,weekday))
    rows = cur.fetchall() #複数行を取得
    cone.close()
    return rows

#[M7-1]記録する「前」に呼ぶ: その種目の「過去最高」と「前回(今日より前)の重量」を返す(自己ベスト判定・前回比用)
#  戻り値: {"max": 過去最高の重量, "last_weight": 前回の重量, "last_date": 前回の日付}   記録が無ければ None が入る
#  ※記録した「後」に呼ぶと、今記録した重量自身が過去最高になってしまうので、必ず記録の前に呼ぶ
def get_previous_records(user_id, exercise, today_str):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT MAX(weight) FROM kintores WHERE user_id = ? AND exercise = ?", (user_id, exercise))
    max_weight = cur.fetchone()[0]                 # 記録が1件も無ければ None
    # created_at < "2026-09-22" = 今日より前の記録だけ。("2026-09-22 10:00:00" は "2026-09-22" より大きい文字列なので、今日の分は含まれない)
    cur.execute("""
        SELECT weight, substr(created_at, 1, 10) FROM kintores
        WHERE user_id = ? AND exercise = ? AND created_at < ?
        ORDER BY created_at DESC, id DESC LIMIT 1
    """, (user_id, exercise, today_str))
    last = cur.fetchone()                          # (重量, 日付) or None
    cone.close()
    return {"max": max_weight,
            "last_weight": last[0] if last else None,
            "last_date": last[1] if last else None}

#[M7-2]成長ダッシュボード用: 種目ごと・日ごとの最大重量を、全期間ぶん返す
#  戻り値: {"ロウマシン": [("2026-09-15", 50.0), ("2026-09-18", 55.0)], ...}  (日付の古い順)
#  GROUP BY 種目, 日付 = 同じ日に同じ種目を何回か記録していても、その日の最大重量1つにまとめる
def get_growth_data(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("""
        SELECT exercise, substr(created_at, 1, 10) AS d, MAX(weight) FROM kintores
        WHERE user_id = ?
        GROUP BY exercise, d
        ORDER BY exercise, d
    """, (user_id,))
    rows = cur.fetchall()
    cone.close()
    data = {}
    for exercise, d, weight in rows:
        data.setdefault(exercise, []).append((d, weight))   # setdefault = キーが無ければ空リストを作ってから、それを返す(辞書のグループ化の定番)
    return data

#[M8-1]経験値(XP)を増やす。amount=増える量 / reason=内訳の文章(例: "種目50・来た日20") / 記録は1回ごとに1行ずつ残す(履歴として見返せる)
def add_xp(user_id, amount, reason, created_at):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("INSERT INTO xp_log(user_id, amount, reason, created_at) VALUES(?,?,?,?)", (user_id, amount, reason, created_at))
    cone.commit()
    cone.close()

#[M8-2]累計の経験値を返す。COALESCE(SUM(amount), 0) = 合計。1行も無い時は SUM が NULL になるので、0にする
def get_total_xp(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM xp_log WHERE user_id = ?", (user_id,))
    total = cur.fetchone()[0]
    cone.close()
    return total

#[M8-3]経験値の履歴が何行あるか(0行なら、まだ一度も経験値を付けていない=過去の記録ぶんを付け足す対象)
def count_xp_entries(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT COUNT(*) FROM xp_log WHERE user_id = ?", (user_id,))
    n = cur.fetchone()[0]
    cone.close()
    return n

#[M8-4]これまでの記録の「件数」と「記録した日数」を返す(過去の記録ぶんの経験値を計算するため)
def get_record_stats(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT substr(created_at, 1, 10)) FROM kintores WHERE user_id = ?", (user_id,))
    count, days = cur.fetchone()
    cone.close()
    return count, days

#[M2-6]プランが登録されている曜日の一覧を返す(曜日切り替えプルダウン用) 例: [1, 2, 5, 6]
#  DISTINCT = 重複を除く。ORDER BY weekday = 月(0)〜日(6)の順に並べる
def get_plan_weekdays(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT DISTINCT weekday FROM plans WHERE user_id = ? ORDER BY weekday", (user_id,))
    rows = cur.fetchall()          # [(1,), (2,), (5,), (6,)] のようなタプルのリスト
    cone.close()
    return [r[0] for r in rows]    # タプルから数字だけ取り出して [1, 2, 5, 6] にする

#[M6-1]指定した日の記録を「id付き」で取得する(記録の削除・修正UI用)  古い順
#  戻り値: [(id, 部位, 種目, 重量, 記録日時), ...]   id = その記録を1件だけ指定するための番号
def get_records_with_id(user_id, date_str):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("""
        SELECT id, body_part, exercise, weight, created_at FROM kintores
        WHERE user_id = ? AND created_at LIKE ?
        ORDER BY id
    """, (user_id, date_str + "%"))
    rows = cur.fetchall()
    cone.close()
    return rows

#[M6-2]idを指定して記録を削除する。user_idも条件に入れて、他の人の記録を消せないようにする。戻り値=実際に削除した件数
def delete_records_by_ids(user_id, ids):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    deleted = 0
    for rid in ids:
        cur.execute("DELETE FROM kintores WHERE id = ? AND user_id = ?", (rid, user_id))
        deleted += cur.rowcount        # rowcount = 直前のSQLで実際に変更された行数(0なら該当なし)
    cone.commit()
    cone.close()
    return deleted

#[M6-3]記録1件の重量を修正する
def update_record_weight(user_id, record_id, weight):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("UPDATE kintores SET weight = ? WHERE id = ? AND user_id = ?", (weight, record_id, user_id))
    cone.commit()
    cone.close()

#[M6-4]プランから、指定した曜日の指定した種目を削除する。戻り値=削除した件数
def delete_plan_exercises(user_id, weekday, exercises):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    deleted = 0
    for ex in exercises:
        cur.execute("DELETE FROM plans WHERE user_id = ? AND weekday = ? AND exercise = ?", (user_id, weekday, ex))
        deleted += cur.rowcount
    cone.commit()
    cone.close()
    return deleted

#[M6-5]曜日ごとのプランの種目数を返す。例: {1: 5, 2: 6, 5: 5, 6: 6}   (プラン編集UIの曜日メニューに表示する)
def get_plan_counts(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT weekday, COUNT(*) FROM plans WHERE user_id = ? GROUP BY weekday", (user_id,))   # GROUP BY = 曜日ごとにまとめて数える
    rows = cur.fetchall()
    cone.close()
    return {wd: n for wd, n in rows}     # [(1,5),(2,6)] → {1:5, 2:6}  (辞書にする書き方)

#[M2-4]planをdbに追加。かつ　同じ曜日・同じ種目があれば重量を更新する [9/20追加]
#p火で、まだ登録されていない種目を新しく追加するとき
#p火を2回送ったときに、種目が重複しないようにするとき
def upsert_plan(user_id, body_part, exercise, weight, sets, weekday):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT id FROM plans WHERE user_id = ? AND weekday = ? AND exercise = ?",
                (user_id, weekday, exercise))
    row = cur.fetchone()
    if row is None:
        cur.execute("""
            INSERT INTO plans(user_id, body_part, exercise, weight, sets, weekday)
            VALUES(?,?,?,?,?,?)
        """, (user_id, body_part, exercise, weight, sets, weekday))
    else:
        cur.execute("UPDATE plans SET weight = ?, body_part = ? WHERE id = ?", (weight, body_part, row[0]))
    cone.commit()
    cone.close()

#[M2-5]その種目の重量を、全曜日のプランで更新する
#モーダルで重量更新したとき共通曜日も更新する
def update_weight_all_weekdays(user_id, exercise, weight):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("UPDATE plans SET weight = ? WHERE user_id = ? AND exercise = ?",
                (weight, user_id, exercise))
    cone.commit()
    cone.close()

#[M4-1]そのユーザーが見つけた画像一覧を取得
def get_imgText(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT DISTINCT image FROM img_texts WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    cone.close()
    return rows

#[M4-2]新しく見つけた画像を記録
def add_imgText(user_id, img):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("INSERT INTO img_texts(user_id, image) VALUES(?, ?)", (user_id, img))
    cone.commit()
    cone.close()

#[M5-1]今日、通知を送ったか(リマインダー or 明日予定)
def is_notified(kind, str_today):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT 1 FROM notified WHERE kind = ? AND sent_date = ?", (kind, str_today))
    row = cur.fetchone() #1行だけ。あれば(1,)
    cone.close()
    return row is not None # rowがある場合は送信済み

#[M5-2]通知を送ったと記録する
def insert_notified(kind, str_today):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("INSERT INTO notified(kind, sent_date) VALUES(?, ?)", (kind, str_today))
    cone.commit()
    cone.close()
              
cone.commit()                       # ④変更を保存（これを忘れると保存されない）
cone.close()                        # ⑤接続を閉じる



# --------削除-----------------
# [M1-4]ユーザーの全部位データ列を取得(部位のexpのため)
# def getBodyParts(user_id):
#     cone = sqlite3.connect("kintore.db")
#     cur = cone.cursor()                 
#     cur.execute(" SELECT body_part FROM kintores WHERE user_id = ?" ,(user_id,))
#          #execute()の第2引数が「?の数だけ値を並べたセット」を受け取るため、タプル表示の,↑
#     bodyPat_rows = cur.fetchall()
#     cone.close()
#     return bodyPat_rows

#[M9-1]獲得済みの勲章を {勲章のキー: 獲得日時} で返す
def get_earned_badges(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT key, earned_at FROM badges_earned WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    cone.close()
    return dict(rows)      # [(key, 日時), ...] → {key: 日時}

#[M9-2]勲章の獲得を記録する。INSERT OR IGNORE = 既に持っている勲章なら、何もしない(エラーにもならない)
def add_earned_badge(user_id, key, earned_at):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("INSERT OR IGNORE INTO badges_earned(user_id, key, earned_at) VALUES(?,?,?)", (user_id, key, earned_at))
    cone.commit()
    cone.close()

#[M9-3]記録した日付("2026-09-22")の一覧を、古い順に返す(連続記録の最長日数を出すため)
def get_gym_dates(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT DISTINCT substr(created_at, 1, 10) FROM kintores WHERE user_id = ? ORDER BY 1", (user_id,))
    dates = [row[0] for row in cur.fetchall()]
    cone.close()
    return dates

#[M9-4]部位ごとの記録件数を {"胸": 12, "脚": 5, ...} で返す(部位マスター用)
def get_body_part_counts(user_id):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT body_part, COUNT(*) FROM kintores WHERE user_id = ? GROUP BY body_part", (user_id,))
    rows = cur.fetchall()
    cone.close()
    return dict(rows)

#[M10-1]今日のログインボーナスの記録を、古い順(1回目から)に返す: [(何回目, 種類, 得た経験値, 表示する文章), ...]
def get_login_pulls(user_id, date_str):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("SELECT n, kind, xp, text FROM login_pulls WHERE user_id = ? AND date = ? ORDER BY n", (user_id, date_str))
    rows = cur.fetchall()
    cone.close()
    return rows

#[M10-2]ログインボーナスを1回押した記録を追加する。戻り値: True=追加できた / False=同じ回が既にある(連打で、同時に押された)
#  IntegrityError = PRIMARY KEY(user_id, date, n) がぶつかった時のエラー
def add_login_pull(user_id, date_str, n, kind, xp, text):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    try:
        cur.execute("INSERT INTO login_pulls(user_id, date, n, kind, xp, text) VALUES(?,?,?,?,?,?)", (user_id, date_str, n, kind, xp, text))
        cone.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        cone.close()      # try の中で return しても、finally は必ず実行される

#[M10-3]押した記録の表示文章を書き換える(レベルアップの一言を足すため)
def set_login_pull_text(user_id, date_str, n, text):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("UPDATE login_pulls SET text = ? WHERE user_id = ? AND date = ? AND n = ?", (text, user_id, date_str, n))
    cone.commit()
    cone.close()

#[M10-4]「今日のログインボーナス画面を出した」と記録する。戻り値: True=今日はじめて / False=もう出した
#  INSERT OR IGNORE は、既にあれば何もしない。何行入ったか(rowcount)で、はじめてかどうかが分かる
def claim_login_panel(user_id, date_str):
    cone = sqlite3.connect("kintore.db")
    cur = cone.cursor()
    cur.execute("INSERT OR IGNORE INTO login_panels(user_id, date) VALUES(?,?)", (user_id, date_str))
    cone.commit()
    first = cur.rowcount == 1
    cone.close()
    return first
