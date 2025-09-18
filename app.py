#!/usr/bin/env python3

from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import json
import csv
from pathlib import Path

APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "data.json"
CSV_FILE = APP_DIR / "classifica.csv"

app = Flask(__name__)
app.secret_key = "replace_this_with_a_random_secret"  # serve per flash messages

# ---------------- utility: salva/leggi stato ----------------
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# ---------------- generatore calendario (round-robin) ----------------
def crea_calendario(players):
    players = [p.strip() for p in players if p.strip()]
    if len(players) == 0:
        return []
    if len(players) % 2 == 1:
        players.append("Riposo")
    n = len(players)
    rounds = n - 1
    arr = players[:]
    calendario = []
    for r in range(rounds):
        match_list = []
        for i in range(n // 2):
            home = arr[i]
            away = arr[n - 1 - i]
            match_list.append({
                "home": home,
                "away": away,
                "home_goals": None,
                "away_goals": None
            })
        calendario.append(match_list)
        # ruota (circle method)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return calendario

# ---------------- calcola classifica ----------------
def compute_standings(schedule):
    stats = {}
    for rnd in schedule:
        for m in rnd:
            if m["home"] != "Riposo":
                stats.setdefault(m["home"], {"V":0,"P":0,"S":0,"DR":0,"Pts":0})
            if m["away"] != "Riposo":
                stats.setdefault(m["away"], {"V":0,"P":0,"S":0,"DR":0,"Pts":0})
    for rnd in schedule:
        for m in rnd:
            if m["home"] == "Riposo" or m["away"] == "Riposo":
                continue
            if m["home_goals"] is None or m["away_goals"] is None:
                continue
            hg = int(m["home_goals"])
            ag = int(m["away_goals"])
            if hg > ag:
                stats[m["home"]]["V"] += 1
                stats[m["away"]]["S"] += 1
                stats[m["home"]]["Pts"] += 3
            elif hg < ag:
                stats[m["away"]]["V"] += 1
                stats[m["home"]]["S"] += 1
                stats[m["away"]]["Pts"] += 3
            else:
                stats[m["home"]]["P"] += 1
                stats[m["away"]]["P"] += 1
                stats[m["home"]]["Pts"] += 1
                stats[m["away"]]["Pts"] += 1
            stats[m["home"]]["DR"] += (hg - ag)
            stats[m["away"]]["DR"] += (ag - hg)
    return stats

# ---------------- salva CSV ----------------
def save_csv(stats):
    headers = ["Giocatore","Vittorie","Pareggi","Sconfitte","Differenza Reti","Punti"]
    rows = sorted(stats.items(), key=lambda kv: (-kv[1]["Pts"], -kv[1]["DR"], kv[0]))
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for player, s in rows:
            writer.writerow([player, s["V"], s["P"], s["S"], s["DR"], s["Pts"]])

# ---------------- routes ----------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/create", methods=["POST"])
def create():
    raw = request.form.get("players", "")
    if "\n" in raw or "\r" in raw:
        players = [line.strip() for line in raw.splitlines() if line.strip()]
    else:
        players = [p.strip() for p in raw.split(",") if p.strip()]
    if len(players) < 2:
        flash("Inserisci almeno 2 giocatori (separati da newline o virgola).")
        return redirect(url_for("index"))
    calendario = crea_calendario(players)
    data = {"players": players, "schedule": calendario}
    save_data(data)
    standings = compute_standings(calendario)
    save_csv(standings)
    flash("Torneo creato con successo.")
    return redirect(url_for("tournament"))

@app.route("/tournament", methods=["GET"])
def tournament():
    data = load_data()
    if not data:
        flash("Nessun torneo creato. Crea uno nuovo.")
        return redirect(url_for("index"))

    # Prepara schedule compatibile con template
    schedule_with_index = []
    for i, turno in enumerate(data["schedule"]):
        matches_with_index = []
        for j, m in enumerate(turno):
            matches_with_index.append({
                "match_idx": j,
                "home": m["home"],
                "away": m["away"],
                "home_goals": m["home_goals"],
                "away_goals": m["away_goals"]
            })
        schedule_with_index.append({
            "round_idx": i,
            "matches": matches_with_index
        })

    standings = compute_standings(data["schedule"])
    save_csv(standings)
    return render_template("tournament.html", schedule=schedule_with_index, standings=standings)

@app.route("/submit_result", methods=["POST"])
def submit_result():
    data = load_data()
    if not data:
        flash("Nessun torneo caricato.")
        return redirect(url_for("index"))
    try:
        round_idx = int(request.form["round_idx"])
        match_idx = int(request.form["match_idx"])
        hg_raw = request.form.get("home_goals", "")
        ag_raw = request.form.get("away_goals", "")

        # rimuove spazi e controlla validità numerica
        hg_str = hg_raw.strip()
        ag_str = ag_raw.strip()
        if not hg_str.isdigit() or not ag_str.isdigit():
            flash(f"Errore: inserisci solo numeri interi validi. Hai inserito '{hg_raw}' e '{ag_raw}'")
            return redirect(url_for("tournament"))

        hg = int(hg_str)
        ag = int(ag_str)

        data["schedule"][round_idx][match_idx]["home_goals"] = hg
        data["schedule"][round_idx][match_idx]["away_goals"] = ag
        save_data(data)
        standings = compute_standings(data["schedule"])
        save_csv(standings)
        flash("Risultato salvato e classifica aggiornata.")
    except Exception as e:
        flash(f"Errore inatteso: {e}")
    return redirect(url_for("tournament"))

@app.route("/standings")
def standings():
    data = load_data()
    if not data:
        flash("Nessun torneo creato.")
        return redirect(url_for("index"))
    stats = compute_standings(data["schedule"])
    return render_template("standings.html", stats=stats)

@app.route("/download_csv")
def download_csv():
    if not CSV_FILE.exists():
        flash("File CSV non trovato. Genera la classifica prima.")
        return redirect(url_for("tournament"))
    return send_file(CSV_FILE, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
