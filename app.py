import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request

app = Flask(__name__)

# 🔧 AUTOMATIC RULES
MAX_ORDERS_PER_DAY = 10          # Rule 1: 10 orders/day
TRADING_START = dtime(9, 25)     # Rule 2: Start time
TRADING_END = dtime(15, 0)       # Rule 2: End time
CHECK_INTERVAL = 30              # Auto check every 30 sec

# 💾 State Management
STATE_FILE = 'state.json'

# ==================== AUTOMATIC FUNCTIONS ====================

def load_state():
    """Load automatic state"""
    default_state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'auto_monitoring': True
    }
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                saved = json.load(f)
                # New day = reset
                if saved.get('date') != default_state['date']:
                    return default_state
                return saved
    except:
        pass
    
    return default_state

def save_state(state):
    """Save automatic state"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def is_trading_time():
    """Automatic time check"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def auto_check_all_rules():
    """Check ALL 3 rules automatically"""
    state = load_state()
    now = datetime.now()
    current_time = now.strftime('%H:%M:%S')
    
    print(f"⏰ AUTO CHECK: {current_time}")
    
    # RULE 1: Daily Reset
    if state['date'] != now.strftime('%Y-%m-%d'):
        print("🔄 AUTO: New day - Reset all counters")
        state = {
            'date': now.strftime('%Y-%m-%d'),
            'order_count': 0,
            'trading_allowed': True,
            'blocked_reason': '',
            'auto_monitoring': True
        }
        save_state(state)
        return
    
    # RULE 2: Trading Hours Check (9:25-15:00)
    if not is_trading_time():
        if state['trading_allowed']:
            print("🕒 AUTO: Outside trading hours (9:25-15:00)")
            state['trading_allowed'] = False
            state['blocked_reason'] = 'Outside trading hours (9:25-15:00)'
            save_state(state)
    else:
        # Inside trading hours - check other rules
        if not state['trading_allowed'] and state['blocked_reason'] == 'Outside trading hours (9:25-15:00)':
            print("✅ AUTO: Trading hours started - Allowing trades")
            state['trading_allowed'] = True
            state['blocked_reason'] = ''
            save_state(state)
    
    # RULE 3: Order Count Check
    if state['order_count'] >= MAX_ORDERS_PER_DAY:
        if state['trading_allowed']:
            print(f"🔢 AUTO: {MAX_ORDERS_PER_DAY} ORDERS LIMIT REACHED!")
            state['trading_allowed'] = False
            state['blocked_reason'] = f'{MAX_ORDERS_PER_DAY} orders per day limit'
            save_state(state)

def automatic_monitor():
    """Main automatic monitoring loop"""
    print("🤖 AUTOMATIC MONITOR STARTED")
    print(f"✅ RULES: 10 orders/day, Time: 9:25-15:00")
    
    while True:
        try:
            auto_check_all_rules()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"❌ Auto monitor error: {e}")
            time.sleep(60)

# Start automatic monitor thread
monitor_thread = threading.Thread(target=automatic_monitor, daemon=True)
monitor_thread.start()

# ==================== WEB ROUTES ====================

@app.route('/')
def dashboard():
    """Automatic System Dashboard"""
    state = load_state()
    trading_now = is_trading_time()
    
    return jsonify({
        'system': '🚀 FULLY AUTOMATIC TRADE MANAGER',
        'status': 'ACTIVE ✅',
        'version': 'NO-BALANCE-1.0',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        
        'automatic_rules': {
            '1_10_orders_per_day': {
                'status': 'ENABLED 🛡️',
                'current': state['order_count'],
                'limit': MAX_ORDERS_PER_DAY,
                'remaining': MAX_ORDERS_PER_DAY - state['order_count']
            },
            '2_trading_hours': {
                'status': 'ENABLED 🛡️',
                'time_range': '9:25 AM - 3:00 PM',
                'current_status': 'OPEN ✅' if trading_now else 'CLOSED 🔒',
                'current_time': datetime.now().strftime('%H:%M')
            },
            '3_auto_monitoring': {
                'status': 'ACTIVE 🤖',
                'check_interval': f'{CHECK_INTERVAL} seconds'
            }
        },
        
        'current_state': {
            'trading_allowed': 'YES ✅' if state['trading_allowed'] else 'NO 🔴',
            'blocked_reason': state['blocked_reason'] or 'None',
            'today_date': state['date'],
            'orders_today': state['order_count'],
            'auto_monitoring': 'ACTIVE' if state.get('auto_monitoring', True) else 'INACTIVE'
        },
        
        'actions': {
            'simulate_order': '/simulate_order (GET) - Test order count',
            'force_reset': '/reset (GET) - Reset all counters',
            'check_health': '/health (GET) - System health',
            'toggle_trading': '/toggle_trading?allow=true|false (GET) - Manual override'
        }
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'HEALTHY ✅',
        'auto_system': 'RUNNING 🤖',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/simulate_order')
def simulate_order():
    """Simulate an order (for testing automatic counting)"""
    state = load_state()
    
    if not state['trading_allowed']:
        return jsonify({
            'error': 'TRADING_BLOCKED',
            'reason': state['blocked_reason'],
            'action_required': 'Wait for next day or reset'
        })
    
    # Increase order count
    state['order_count'] += 1
    save_state(state)
    
    # Auto-check if limit reached
    if state['order_count'] >= MAX_ORDERS_PER_DAY:
        state['trading_allowed'] = False
        state['blocked_reason'] = f'{MAX_ORDERS_PER_DAY} orders per day limit'
        save_state(state)
    
    return jsonify({
        'status': 'ORDER_SIMULATED',
        'order_count': state['order_count'],
        'limit': MAX_ORDERS_PER_DAY,
        'remaining': MAX_ORDERS_PER_DAY - state['order_count'],
        'warning': 'LIMIT_REACHED' if state['order_count'] >= MAX_ORDERS_PER_DAY else 'OK'
    })

@app.route('/reset')
def reset_all():
    """Reset all automatic counters"""
    state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'auto_monitoring': True
    }
    save_state(state)
    
    return jsonify({
        'status': 'AUTO_SYSTEM_RESET',
        'message': 'All counters reset to zero',
        'order_count': 0,
        'trading_allowed': True
    })

@app.route('/toggle_trading')
def toggle_trading():
    """Manually override trading status (for emergencies)"""
    allow = request.args.get('allow', 'true').lower() == 'true'
    
    state = load_state()
    state['trading_allowed'] = allow
    state['blocked_reason'] = '' if allow else 'Manually blocked by user'
    save_state(state)
    
    return jsonify({
        'status': 'TRADING_OVERRIDE',
        'trading_allowed': allow,
        'message': 'Manual override applied'
    })

@app.route('/status')
def status():
    """Quick status check"""
    state = load_state()
    
    return jsonify({
        'trading_allowed': state['trading_allowed'],
        'orders_today': state['order_count'],
        'orders_remaining': MAX_ORDERS_PER_DAY - state['order_count'],
        'time_check': is_trading_time(),
        'current_time': datetime.now().strftime('%H:%M:%S')
    })

# ==================== START SERVER ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    
    print("=" * 60)
    print("🤖 FULLY AUTOMATIC TRADE MANAGER")
    print("=" * 60)
    print("✅ NO BALANCE REQUIRED - PURE RULES BASED")
    print("=" * 60)
    print("🛡️ AUTOMATIC PROTECTIONS:")
    print(f"   1. {MAX_ORDERS_PER_DAY} Orders per day")
    print("   2. Trading Hours: 9:25 AM - 3:00 PM")
    print(f"   3. Auto-monitoring every {CHECK_INTERVAL} seconds")
    print("=" * 60)
    print("📊 ENDPOINTS:")
    print("   /           - Dashboard")
    print("   /health     - System health")
    print("   /status     - Quick status")
    print("   /simulate_order - Test order counting")
    print("   /reset      - Reset all counters")
    print("=" * 60)
    print(f"🌐 Starting on port {port}...")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
