import os
import time
import json
import threading
import requests
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request

# ==================== CONFIG ====================
app = Flask(__name__)

# 🔧 AUTOMATIC SETTINGS
MAX_ORDERS_PER_DAY = 10
MAX_LOSS_PERCENT = 0.20
TRADING_START = dtime(9, 25)
TRADING_END = dtime(15, 0)
CHECK_INTERVAL = 30

# 🔑 Dhan API (Set in Render Environment Variables)
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', 'demo_token')
HEADERS = {'access-token': ACCESS_TOKEN}

# 💾 State
STATE_FILE = 'state.json'

# ==================== CORE FUNCTIONS ====================

def load_state():
    """Load state from file"""
    default_state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': ''
    }
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                saved = json.load(f)
                if saved.get('date') == default_state['date']:
                    return saved
    except:
        pass
    
    return default_state

def save_state(state):
    """Save state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def is_trading_time():
    """Check if within trading hours"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def get_dhan_balance():
    """Get balance from Dhan API"""
    try:
        # Try different endpoints
        endpoints = [
            'https://api.dhan.co/positions',
            'https://api.dhan.co/funds',
            'https://api.dhan.co/account'
        ]
        
        for url in endpoints:
            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Try to extract balance
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    
                    if isinstance(data, dict):
                        # Check common balance fields
                        balance_fields = [
                            'netAvailableMargin', 'availableMargin',
                            'balance', 'cashBalance', 'funds'
                        ]
                        
                        for field in balance_fields:
                            if field in data:
                                try:
                                    balance = float(data[field])
                                    if balance > 0:
                                        print(f"✅ Balance found: ₹{balance}")
                                        return balance
                                except:
                                    pass
            except:
                continue
        
        return None
    except Exception as e:
        print(f"❌ Balance fetch error: {e}")
        return None

def check_auto_conditions():
    """Check all automatic conditions"""
    state = load_state()
    
    # 1. Check date (daily reset)
    today = datetime.now().strftime('%Y-%m-%d')
    if state['date'] != today:
        print("🔄 New day - Resetting state")
        state = {
            'date': today,
            'morning_balance': None,
            'max_loss_amount': None,
            'order_count': 0,
            'trading_allowed': True,
            'blocked_reason': ''
        }
        save_state(state)
    
    # 2. Check trading time
    if not is_trading_time():
        if state['trading_allowed']:
            print("⏰ Outside trading hours - Blocking")
            state['trading_allowed'] = False
            state['blocked_reason'] = 'Outside 9:25-15:00'
            save_state(state)
        return
    
    # 3. Morning balance capture (if not captured)
    if state['morning_balance'] is None:
        print("🌅 Capturing morning balance...")
        balance = get_dhan_balance()
        if balance:
            state['morning_balance'] = balance
            state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
            save_state(state)
            print(f"💰 Morning Balance: ₹{balance}")
            print(f"📊 20% Loss Limit: ₹{state['max_loss_amount']}")
    
    # 4. Check 20% loss limit
    if state['morning_balance']:
        current_balance = get_dhan_balance()
        if current_balance:
            loss = state['morning_balance'] - current_balance
            print(f"📈 Current: ₹{current_balance}, Loss: ₹{loss}")
            
            if loss >= state['max_loss_amount'] and state['trading_allowed']:
                print(f"🚨 20% LOSS LIMIT HIT! ₹{loss}")
                state['trading_allowed'] = False
                state['blocked_reason'] = f'20% Loss: ₹{loss}'
                save_state(state)
                # Auto emergency actions can be added here
    
    # 5. Check order limit
    if state['order_count'] >= MAX_ORDERS_PER_DAY and state['trading_allowed']:
        print(f"🔢 {MAX_ORDERS_PER_DAY} ORDERS LIMIT REACHED!")
        state['trading_allowed'] = False
        state['blocked_reason'] = f'{MAX_ORDERS_PER_DAY} Orders Limit'
        save_state(state)

# ==================== AUTO MONITOR THREAD ====================

def auto_monitor_thread():
    """Background thread for automatic monitoring"""
    print("🤖 Starting AUTO Monitor...")
    while True:
        try:
            check_auto_conditions()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"❌ Monitor error: {e}")
            time.sleep(60)

# Start monitor thread
monitor_thread = threading.Thread(target=auto_monitor_thread, daemon=True)
monitor_thread.start()

# ==================== WEB ROUTES ====================

@app.route('/')
def home():
    state = load_state()
    return jsonify({
        'system': 'AUTO DHAN Risk Manager',
        'status': 'RUNNING 🟢',
        'time': datetime.now().strftime('%H:%M:%S'),
        'trading_hours': '9:25-15:00',
        'auto_protections': {
            '20%_loss_limit': 'ACTIVE',
            '10_orders_per_day': 'ACTIVE',
            'time_check': 'ACTIVE'
        },
        'today': {
            'date': state['date'],
            'morning_balance': state['morning_balance'],
            'max_loss_20%': state['max_loss_amount'],
            'orders_today': state['order_count'],
            'trading_allowed': state['trading_allowed'],
            'blocked_reason': state['blocked_reason']
        },
        'endpoints': {
            '/health': 'System health',
            '/balance': 'Check balance',
            '/simulate_order': 'Test order count',
            '/reset': 'Reset day'
        }
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'OK',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/balance')
def balance():
    bal = get_dhan_balance()
    return jsonify({'balance': bal})

@app.route('/simulate_order')
def simulate_order():
    state = load_state()
    state['order_count'] += 1
    save_state(state)
    return jsonify({
        'simulated': True,
        'order_count': state['order_count'],
        'limit': MAX_ORDERS_PER_DAY
    })

@app.route('/reset')
def reset():
    state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': ''
    }
    save_state(state)
    return jsonify({'reset': True})

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print("=" * 50)
    print("🤖 AUTO DHAN RISK MANAGER")
    print("=" * 50)
    print("✅ Auto Protections:")
    print("   • 20% Daily Loss Limit")
    print("   • 10 Orders/Day Limit")
    print("   • 9:25-15:00 Trading Hours")
    print("=" * 50)
    print(f"🌐 Server starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
