from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import json
import time
from datetime import datetime, timedelta
import threading
import os
import logging
from logging.handlers import RotatingFileHandler
import sys

# Настройка логирования

rotating_handler = RotatingFileHandler(
    'logs/tournament.log', 
    maxBytes= 10 * 1024 * 1024,  # 10 МБ - размер, при превышении ротируется
    backupCount = 5  # Хранить до 5 старых файлов, старые удаляются автоматически
)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        rotating_handler
    ]
)

app = Flask(__name__)
app.secret_key = 'super_secret_key'  # Change to a real secret

# Hardcoded admin password (change it)
ADMIN_PASSWORD = 'admin123'

# Часовой пояс (смещение в часах от UTC)
TIMEZONE_OFFSET = 4  # UTC+4 для Саратова

# Data file
DATA_FILE = 'tournament.json'

# Tournament data
tournament_data = {
    'start_time': None,  # datetime ISO string
    'levels': [],  # list of {'type': 'level' or 'break', 'duration': int minutes, 'small_blind': int, 'big_blind': int} for levels, blinds=0 for breaks
    'current_index': 0,
    'remaining_time': 0,  # seconds
    'paused': False,
    'players': 0,
    'max_players': 0,
    'chips_in_play': 0,
    'starting_stack': 10000,
    'rebuy_stack': 10000,
    'addon_chips': 100000,
    'rebuys_count': 0,
    'addons_count': 0,
    'finished': False,
    'next_start_time': None,
}

def recalculate_chips():
    """Пересчитывает chips_in_play на основе max_players, ребаев и аддонов"""
    tournament_data['chips_in_play'] = (
        tournament_data['max_players'] * tournament_data['starting_stack']
        + tournament_data['rebuys_count'] * tournament_data['rebuy_stack']
        + tournament_data['addons_count'] * tournament_data['addon_chips']
    )
    logging.info(f"Chips recalculated: {tournament_data['chips_in_play']}")
    save_data()

def save_data():
    try:
        with open(DATA_FILE, 'w') as f:
            data = tournament_data.copy()
            if data['start_time']:
                data['start_time'] = data['start_time'].strftime('%Y-%m-%dT%H:%M:%S')
            else:
                data['start_time'] = None
            if data['next_start_time']:
                data['next_start_time'] = data['next_start_time'].strftime('%Y-%m-%dT%H:%M:%S')
            else:
                data['next_start_time'] = None
            json.dump(data, f)
            logging.debug(f"Data saved successfully. Start time: {data['start_time']}")
    except Exception as e:
        logging.error(f"Error saving data: {e}", exc_info=True)

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                if data['start_time']:
                    try:
                        data['start_time'] = datetime.strptime(data['start_time'], '%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        logging.error("Invalid datetime format in saved data")
                        data['start_time'] = None
                if 'next_start_time' in data and data['next_start_time']:
                    try:
                        data['next_start_time'] = datetime.strptime(data['next_start_time'], '%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        logging.error("Invalid next_start_time format")
                        data['next_start_time'] = None
                else:
                    data['next_start_time'] = None

                if 'finished' not in data:
                    data['finished'] = False
                
                # Установка значений по умолчанию для отсутствующих полей
                defaults = {
                    'rebuys_count': 0,
                    'addons_count': 0,
                    'rebuy_stack': 40000,
                    'paused': False,
                    'remaining_time': 0,
                    'max_players': 0,
                }
                
                for key, default_value in defaults.items():
                    if key not in data:
                        data[key] = default_value
                
                global tournament_data
                tournament_data = data

                if tournament_data['max_players'] < tournament_data['players']: # После загрузки данных добавляем количество максимальных игроков
                    tournament_data['max_players'] = tournament_data['players']

                # Пересчитываем фишки при загрузке
                recalculate_chips()
                
                logging.info(f"Data loaded successfully. Start time: {data['start_time']}")
    except Exception as e:
        logging.error(f"Error loading data: {e}", exc_info=True)

load_data()

# Server-side timer thread
def timer_thread():
    logging.info("Timer thread started")
    last_tick = time.time()
    while True:
        try:
            current_time = datetime.now()
            now = time.time()
            
            if not tournament_data['paused'] and tournament_data['start_time']:
                logging.debug(f"Current time: {current_time}, Start time: {tournament_data['start_time']}")
                
                # Проверяем, начался ли турнир
                if tournament_data['start_time'] <= current_time:
                    if tournament_data['remaining_time'] > 0:
                        tournament_data['remaining_time'] -= 1
                        logging.debug(f"Time remaining: {tournament_data['remaining_time']}")
                        
                        # Если время закончилось, проверяем текущий уровень
                        if tournament_data['remaining_time'] == 0:
                            current_index = tournament_data['current_index']
                            levels = tournament_data['levels']
                            current = levels[current_index]
                            
                            logging.info(f"Level ended: {current_index}")
                            
                            # Если это был последний уровень, оставляем на паузе
                            if current_index >= len(levels) - 1:
                                tournament_data['paused'] = True
                                save_data()
                                logging.info("Tournament ended")
                                continue
                            
                            # Автоматически переходим к следующему уровню
                            tournament_data['current_index'] += 1
                            next_level = levels[tournament_data['current_index']]
                            tournament_data['remaining_time'] = next_level['duration'] * 60
                            
                            logging.info(f"Moving to next level: {tournament_data['current_index']}")
                            
                            # Если закончился обычный уровень и начинается перерыв,
                            # или закончился перерыв и начинается обычный уровень,
                            # ставим на паузу для подтверждения админом
                            if (current['type'] == 'level' and next_level['type'] == 'break') or \
                               (current['type'] == 'break' and next_level['type'] == 'level'):
                                tournament_data['paused'] = True
                                logging.info("Paused for level type change")
                        save_data()
        except Exception as e:
            logging.error(f"Error in timer thread: {e}", exc_info=True)
            
        # Вычисляем точное время для следующего тика
        target_time = last_tick + 1.0
        sleep_time = max(0, target_time - time.time())
        time.sleep(sleep_time)
        last_tick = target_time

threading.Thread(target=timer_thread, daemon=True).start()

# Client page
@app.route('/')
def client():
    return render_template('client.html')

# API for state
@app.route('/api/state')
def api_state():
    if tournament_data['finished'] and tournament_data['next_start_time'] and tournament_data['next_start_time'] < datetime.utcnow():
        tournament_data['finished'] = False
        tournament_data['next_start_time'] = None
        
        # === ЗАПУСК НОВОГО ТУРНИРА ===
        if tournament_data['levels']:
            tournament_data['start_time'] = datetime.utcnow()
            tournament_data['current_index'] = 0
            level = tournament_data['levels'][0]
            tournament_data['remaining_time'] = level['duration'] * 60
            tournament_data['paused'] = True
            logging.info("Tournament auto-started after finish.")
        else:
            logging.warning("Cannot start tournament: no levels defined.")
        
        save_data()

    if tournament_data['levels']:
        current = tournament_data['levels'][tournament_data['current_index']]
        is_break = current['type'] == 'break'
        
        # Для перерыва номер уровня не показываем
        level_num = sum(1 for lev in tournament_data['levels'][:tournament_data['current_index']+1] if lev['type'] == 'level') if not is_break else '-'
        
        # Для перерыва блайнды не показываем
        blinds = f"{current.get('small_blind', 0)} / {current.get('big_blind', 0)}" if not is_break else '-'
        
        # Получаем информацию о следующем уровне
        next_index = tournament_data['current_index'] + 1
        if next_index < len(tournament_data['levels']):
            next_level_data = tournament_data['levels'][next_index]
            # Если следующий уровень - перерыв
            if next_level_data['type'] == 'break':
                next_level = 'Перерыв'
                next_blinds = f"{next_level_data['duration']} мин"
            else:
                # Ищем следующий уровень с блайндами
                level_count = sum(1 for lev in tournament_data['levels'][:next_index+1] if lev['type'] == 'level')
                next_level = level_count
                next_blinds = f"{next_level_data['small_blind']} / {next_level_data['big_blind']}"
        else:
            next_level = '-'
            next_blinds = '-'
            
        # Вычисляем средний стек
        avg_stack = int(tournament_data['chips_in_play'] / tournament_data['players']) if tournament_data['players'] > 0 else 0
        big_blind = current.get('big_blind', 0) if tournament_data['levels'] and not is_break else 0 # Для вычисления среднего стека в больших блайндах
        avg_stack_bb = round(avg_stack / big_blind, 1) if big_blind > 0 else '-'
    else:
        is_break = False
        level_num = '-'
        blinds = '-'
        next_level = '-'
        next_blinds = '-'
        avg_stack = 0
        
    response_data = {
        'level': level_num,
        'blinds': blinds,
        'is_break': is_break,
        'remaining': tournament_data['remaining_time'],
        'players': tournament_data['players'],
        'max_players': tournament_data['max_players'],
        'chips': int(tournament_data['chips_in_play']),
        'avg_stack': avg_stack,
        'avg_stack_bb': avg_stack_bb,
        'paused': tournament_data['paused'],
        'next_level': next_level,
        'next_blinds': next_blinds,
        'rebuys_count': tournament_data['rebuys_count'],
        'addons_count': tournament_data['addons_count'],
        'starting_stack': tournament_data['starting_stack'],
        'rebuy_stack': tournament_data['rebuy_stack'],
        'addon_chips': tournament_data['addon_chips'],
        'finished': tournament_data['finished'],
        'next_start_time': tournament_data['next_start_time'].strftime('%Y-%m-%dT%H:%M:%S') if tournament_data['next_start_time'] else None,
    }

    # Если запрос от XHR (AJAX), отправляем полные данные
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(response_data)
    
    # Для обычных запросов отправляем только базовые данные
    return jsonify({k: v for k, v in response_data.items() if k not in 
        ['rebuys_count', 'addons_count', 'starting_stack', 'rebuy_stack', 'addon_chips']})

# Admin login
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin'))
        return redirect(url_for('admin_login', error='1'))
    return '''
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Вход в админ-панель</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }

                body {
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    font-family: 'Roboto', Arial, sans-serif;
                    padding: 20px;
                }

                .login-container {
                    background: rgba(255, 255, 255, 0.05);
                    backdrop-filter: blur(10px);
                    padding: 2rem;
                    border-radius: 15px;
                    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    width: 100%;
                    max-width: 400px;
                    transform: translateY(0);
                    transition: transform 0.3s ease, box-shadow 0.3s ease;
                }

                .login-container:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.45);
                }

                .login-header {
                    text-align: center;
                    margin-bottom: 2rem;
                    color: #4ecca3;
                }

                .login-header h1 {
                    font-size: 1.8rem;
                    margin-bottom: 0.5rem;
                    text-shadow: 0 0 20px rgba(78, 204, 163, 0.5);
                }

                .login-form {
                    display: flex;
                    flex-direction: column;
                    gap: 1.5rem;
                }

                .form-group {
                    position: relative;
                }

                .form-group input {
                    width: 100%;
                    padding: 1rem;
                    background: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 8px;
                    color: #fff;
                    font-size: 1rem;
                    transition: all 0.3s ease;
                }

                .form-group input:focus {
                    outline: none;
                    border-color: #4ecca3;
                    box-shadow: 0 0 15px rgba(78, 204, 163, 0.3);
                }

                .form-group input::placeholder {
                    color: rgba(255, 255, 255, 0.5);
                }

                .submit-btn {
                    background: linear-gradient(45deg, #4ecca3, #45b08c);
                    color: #fff;
                    border: none;
                    padding: 1rem;
                    border-radius: 8px;
                    font-size: 1rem;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
                }

                .submit-btn:hover {
                    background: linear-gradient(45deg, #45b08c, #4ecca3);
                    box-shadow: 0 0 20px rgba(78, 204, 163, 0.5);
                    transform: translateY(-2px);
                }

                @keyframes shake {
                    0%, 100% { transform: translateX(0); }
                    25% { transform: translateX(-5px); }
                    75% { transform: translateX(5px); }
                }

                .error .form-group input {
                    border-color: #ff6b6b;
                    animation: shake 0.3s ease-in-out;
                }

                @media (max-width: 480px) {
                    .login-container {
                        padding: 1.5rem;
                    }

                    .login-header h1 {
                        font-size: 1.5rem;
                    }

                    .form-group input,
                    .submit-btn {
                        padding: 0.8rem;
                    }
                }
            </style>
        </head>
        <body>
            <div class="login-container">
                <div class="login-header">
                    <h1>Вход в админ-панель</h1>
                </div>
                <form method="post" class="login-form" id="loginForm">
                    <div class="form-group">
                        <input type="password" name="password" placeholder="Введите пароль" required autocomplete="current-password">
                    </div>
                    <button type="submit" class="submit-btn">Войти</button>
                </form>
            </div>
            <script>
                // Добавляем анимацию при ошибке
                if (window.location.search.includes('error')) {
                    document.querySelector('.login-container').classList.add('error');
                    setTimeout(() => {
                        document.querySelector('.login-container').classList.remove('error');
                    }, 1000);
                }

                // Предотвращаем повторную отправку формы
                document.getElementById('loginForm').addEventListener('submit', function(e) {
                    const submitBtn = this.querySelector('.submit-btn');
                    submitBtn.disabled = true;
                    submitBtn.textContent = 'Вход...';
                });
            </script>
        </body>
        </html>
    '''

# Admin panel
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'set_start_time':
            # Преобразуем локальное время в UTC, учитывая смещение часового пояса
            start_time = datetime.fromisoformat(request.form['start_time'])
            tournament_data['start_time'] = start_time - timedelta(hours=TIMEZONE_OFFSET)
            tournament_data['next_start_time'] = None  # Сбрасываем, если запускаем вручную
            tournament_data['finished'] = False
        elif action == 'pause':
            tournament_data['paused'] = not tournament_data['paused']
        elif action == 'set_remaining_time':
            minutes = request.form.get('minutes', type=int)
            seconds = request.form.get('seconds', type=int)
            if minutes is not None and seconds is not None:
                tournament_data['remaining_time'] = minutes * 60 + seconds
        elif action == 'next_level':
            if tournament_data['current_index'] < len(tournament_data['levels']) - 1:
                tournament_data['current_index'] += 1
                tournament_data['remaining_time'] = tournament_data['levels'][tournament_data['current_index']]['duration'] * 60
        elif action == 'prev_level':
            if tournament_data['current_index'] > 0:
                tournament_data['current_index'] -= 1
                tournament_data['remaining_time'] = tournament_data['levels'][tournament_data['current_index']]['duration'] * 60
        elif action == 'set_players':
            new_players = request.form.get('players', type=int)
            if new_players is not None and new_players >= 0:
                old_max = tournament_data['max_players']
                tournament_data['players'] = new_players
                if new_players > old_max:
                    tournament_data['max_players'] = new_players
                    recalculate_chips()
        elif action == 'add_player':
            tournament_data['players'] += 1
            if tournament_data['players'] > tournament_data['max_players']:
                tournament_data['max_players'] = tournament_data['players']
            recalculate_chips()
        elif action == 'remove_player':
            if tournament_data['players'] > 0:
                tournament_data['players'] -= 1
        elif action == 'add_rebuy':
            tournament_data['rebuys_count'] += 1
            recalculate_chips()
        elif action == 'remove_rebuy':
            if tournament_data['rebuys_count'] > 0:
                tournament_data['rebuys_count'] -= 1
            recalculate_chips()
        elif action == 'set_rebuys':
            new_rebuys = request.form.get('rebuys', type=int)
            if new_rebuys is not None and new_rebuys >= 0:
                tournament_data['rebuys_count'] = new_rebuys
            recalculate_chips()
        elif action == 'add_addon':
            tournament_data['addons_count'] += 1
            recalculate_chips()
        elif action == 'remove_addon':
            if tournament_data['addons_count'] > 0:
                tournament_data['addons_count'] -= 1
            recalculate_chips()
        elif action == 'set_addons':
            new_addons = request.form.get('addons', type=int)
            if new_addons is not None and new_addons >= 0:
                tournament_data['addons_count'] = new_addons
            recalculate_chips()
        elif action == 'set_starting_stack':
            new_stack = request.form.get('starting_stack', type=int)
            if new_stack is not None and new_stack >= 0:
                tournament_data['starting_stack'] = new_stack
                recalculate_chips()
        elif action == 'set_rebuy_stack':
            new_stack = request.form.get('rebuy_stack', type=int)
            if new_stack is not None and new_stack >= 0:
                tournament_data['rebuy_stack'] = new_stack
                recalculate_chips()
        elif action == 'set_addon_chips':
            new_chips = request.form.get('addon_chips', type=int)
            if new_chips is not None and new_chips >= 0:
                tournament_data['addon_chips'] = new_chips
                recalculate_chips()
        elif action == 'set_max_players':
            new_max = request.form.get('max_players', type=int)
            if new_max is not None and new_max >= 0:
                tournament_data['max_players'] = new_max
                recalculate_chips()
        elif action == 'update_levels':
            levels = []
            i = 0
            while f'duration_{i}' in request.form:
                is_break = f'is_break_{i}' in request.form
                duration = int(request.form[f'duration_{i}'])
                if is_break:
                    levels.append({'type': 'break', 'duration': duration, 'small_blind': 0, 'big_blind': 0})
                else:
                    small = int(request.form[f'small_{i}'] or 0)
                    big = int(request.form[f'big_{i}'] or 0)
                    levels.append({'type': 'level', 'duration': duration, 'small_blind': small, 'big_blind': big})
                i += 1
            tournament_data['levels'] = levels
            if tournament_data['current_index'] >= len(levels):
                tournament_data['current_index'] = max(0, len(levels) - 1)
            if levels:
                tournament_data['remaining_time'] = levels[tournament_data['current_index']]['duration'] * 60
        elif action == 'add_row':
            # Handled in JS
            pass
        elif action == 'finish_tournament':
            if not tournament_data['finished']:
                if tournament_data['next_start_time'] and tournament_data['next_start_time'] > datetime.utcnow():
                    tournament_data['finished'] = True
                    save_data()
                    logging.info("Tournament finished successfully.")
                else:
                    logging.warning("Cannot finish: next_start_time is in the past or not set.")
        elif action == 'set_next_start':
            next_time_str = request.form.get('next_start_time')
            if next_time_str:
                try:
                    local_dt = datetime.strptime(next_time_str, '%Y-%m-%dT%H:%M')
                    utc_dt = local_dt - timedelta(hours=TIMEZONE_OFFSET)
                    tournament_data['next_start_time'] = utc_dt
                    logging.info(f"Next start time set to {utc_dt} UTC")
                except ValueError:
                    logging.error("Invalid next_start_time format")
            save_data()

    # Копируем данные для шаблона
    template_data = tournament_data.copy()
    if template_data['start_time']:
        # Конвертируем UTC время в локальное для отображения
        template_data['start_time'] = template_data['start_time'] + timedelta(hours=TIMEZONE_OFFSET)
    return render_template('admin.html', data=template_data)

@app.route('/api/export_levels')
def export_levels():
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(tournament_data['levels'])

@app.route('/api/import_levels', methods=['POST'])
def import_levels():
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        levels = request.get_json()
        if not isinstance(levels, list):
            return jsonify({'error': 'Invalid format'}), 400

        for i, lvl in enumerate(levels):
            if not isinstance(lvl, dict):
                return jsonify({'error': f'Level {i} is not an object'}), 400
            if 'type' not in lvl or lvl['type'] not in ['level', 'break']:
                return jsonify({'error': f'Invalid type in level {i}'}), 400
            if 'duration' not in lvl or not isinstance(lvl['duration'], int) or lvl['duration'] <= 0:
                return jsonify({'error': f'Invalid duration in level {i}'}), 400
            if lvl['type'] == 'level':
                if 'small_blind' not in lvl or 'big_blind' not in lvl:
                    return jsonify({'error': f'Missing blinds in level {i}'}), 400

        tournament_data['levels'] = levels
        tournament_data['current_index'] = 0
        if levels:
            tournament_data['remaining_time'] = levels[0]['duration'] * 60
        else:
            tournament_data['remaining_time'] = 0

        save_data()
        logging.info(f"Levels imported: {len(levels)} levels")

        return jsonify({
            'success': True,
            'count': len(levels),
            'levels': levels  
        })
    except Exception as e:
        logging.error(f"Import error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/structure')
def api_structure():
    current_idx = tournament_data['current_index']
    is_break = (current_idx < len(tournament_data['levels']) and 
                tournament_data['levels'][current_idx].get('type') == 'break')
    
    return jsonify({
        'levels': tournament_data['levels'],
        'current_index': current_idx,
        'is_break': is_break,
        'remaining': tournament_data['remaining_time'],
        'updated_at': datetime.now().isoformat()
    })

@app.route('/structure')
def structure_page():
    """Публичная страница: структура турнира"""
    return render_template('structure.html')

if __name__ == '__main__':
    app.run(debug=True)