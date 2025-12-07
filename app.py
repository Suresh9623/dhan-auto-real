import os
import time
import json
import threading
import requests
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler

# ==================== CONFIG ====================
app = Flask(__name__)

# 🔧 तुझे AUTOMATIC SETTINGS
MAX_ORDERS_PER_DAY = 10          # Auto count & block
MAX_LOSS_PERCENT = 0.20          # Auto calculate & exit  
TRADING_START = dtime(9, 25)     # Auto enforce
TRADING_END = dtime(15, 0)       # Auto enforce
BALANCE_CHECK_TIME = dtime(9, 25) # Auto capture
CHECK_INTERVAL = 30              # Auto monitor seconds

# 🔑 Dhan API (Environment Variables मध्ये ठेवा)
CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', 'your_client_id')
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', 'your_token')
HEADERS = {
    'access-token': ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# 💾 State Management
STATE_FILE = 'state.json'
TRADE_LOG_FILE = 'trades.json'

# ==================== CORE AUTO FUNCTIONS ====================

def load_state():
    """Auto load previous state"""
    default_state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'current_balance': None,
        'total_loss': 0,
        'last_check': None,
        'emergency_triggered': False
    }
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                saved = json.load(f)
                # Reset if new day
                if saved.get('date') != default_state['date']:
                    return default_state
                return {**default_state, **saved}
    except:
        pass
    
    return default_state

def save_state(state):
    """Auto save state"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def log_trade(order_data):
    """Auto log every trade for counting"""
    try:
        logs = []
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, 'r') as f:
                logs = json.load(f)
        
        logs.append({
            'timestamp': datetime.now().isoformat(),
            'date': datetime.now().strftime('%Y-%m-%d'),
            **order_data
        })
        
        with open(TRADE_LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=2)
            
        # Auto update order count
        state = load_state()
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = [log for log in logs if log.get('date') == today]
        state['order_count'] = len(today_orders)
        save_state(state)
        
    except Exception as e:
        print(f"❌ Trade log error: {e}")

def is_trading_time():
    """Auto time check"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def smart_get_balance():
    """SMART: Try ALL Dhan endpoints automatically"""
    
    endpoints = [
        '/positions', '/funds', '/margin', 
        '/account', '/limits', '/holdings', '/profile'
    ]
    
    for endpoint in endpoints:
        try:
            print(f"🔍 Auto trying endpoint: {endpoint}")
            response = requests.get(
                f'https://api.dhan.co{endpoint}',
                headers=HEADERS,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ {endpoint} response: {json.dumps(data)[:200]}...")
                
                balance = extract_balance_smart(data)
                if balance and balance > 0:
                    print(f"💰 AUTO Balance found: ₹{balance:,.2f}")
                    return balance
                    
        except Exception as e:
            print(f"❌ {endpoint} failed: {str(e)[:50]}")
            continue
    
    print("⚠️ All endpoints failed - waiting for next try")
    return None

def extract_balance_smart(data):
    """SMART extraction from ANY response format"""
    
    # If list, check first item
    if isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            return extract_balance_smart(data[0])
        return None
    
    if not isinstance(data, dict):
        return None
    
    # All possible balance field names
    balance_fields = [
        'netAvailableMargin', 'availableMargin', 'marginAvailable',
        'balance', 'totalBalance', 'cashBalance', 'netBalance',
        'margin', 'availableCash', 'funds', 'netAmount',
        'available_limit', 'cash_available', 'margin_available',
        'collateral', 'adhoc_margin', 'live_balance'
    ]
    
    # Check direct fields
    for field in balance_fields:
        if field in data:
            try:
                value = float(data[field])
                if value > 0:
                    return value
            except:
                pass
    
    # Check nested structures
    for key, value in data.items():
        if isinstance(value, dict):
            nested = extract_balance_smart(value)
            if nested:
                return nested
        elif isinstance(value, list) and value:
            if isinstance(value[0], dict):
                nested = extract_balance_smart(value[0])
                if nested:
                    return nested
    
    return None

def auto_cancel_all_orders():
    """AUTO cancel all pending orders"""
    print("🛑 AUTO: Cancelling all pending orders...")
    try:
        # Get orders
        response = requests.get(
            'https://api.dhan.co/orders',
            headers=HEADERS,
            timeout=10
        )
        
        if response.status_code == 200:
            orders = response.json()
            for order in orders:
                order_id = order.get('orderId')
                if order_id:
                    # Cancel order
                    cancel_response = requests.delete(
                        f'https://api.dhan.co/orders/{order_id}',
                        headers=HEADERS,
                        timeout=5
                    )
                    if cancel_response.status_code == 200:
                        print(f"✅ Order {order_id} cancelled")
                    else:
                        print(f"❌ Failed to cancel {order_id}")
            return True
    except Exception as e:
        print(f"❌ Cancel orders error: {e}")
    
    return False

def auto_exit_all_positions():
    """AUTO exit all open positions"""
    print("📤 AUTO: Exiting all positions...")
    try:
        # Get positions
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=10
        )
        
        if response.status_code == 200:
            positions = response.json()
            
            for position in positions:
                # Place exit order (market order opposite side)
                symbol = position.get('tradingSymbol')
                quantity = position.get('quantity')
                position_type = position.get('positionType', 'LONG')
                
                if symbol and quantity:
                    # Determine exit side
                    order_side = 'SELL' if position_type == 'LONG' else 'BUY'
                    
                    exit_order = {
                        "securityId": position.get('securityId'),
                        "exchangeSegment": position.get('exchangeSegment', 'NSE_EQ'),
                        "transactionType": order_side,
                        "quantity": quantity,
                        "orderType": "MARKET",
                        "productType": "CNC",
                        "validity": "DAY"
                    }
                    
                    # Place exit order
                    order_response = requests.post(
                        'https://api.dhan.co/orders',
                        headers=HEADERS,
                        json=exit_order,
                        timeout=10
                    )
                    
                    if order_response.status_code == 200:
                        print(f"✅ Exit order placed for {symbol}")
                    else:
                        print(f"❌ Exit failed for {symbol}")
            
            return True
    except Exception as e:
        print(f"❌ Exit positions error: {e}")
    
    return False

def trigger_emergency_actions(reason):
    """AUTO emergency protocol"""
    print(f"🚨🚨🚨 AUTO EMERGENCY TRIGGERED: {reason}")
    
    # 1. Cancel all orders
    auto_cancel_all_orders()
    
    # 2. Exit all positions
    auto_exit_all_positions()
    
    # 3. Block further trading
    state = load_state()
    state['trading_allowed'] = False
    state['blocked_reason'] = reason
    state['emergency_triggered'] = True
    save_state(state)
    
    print(f"🛡️ AUTO: Trading BLOCKED - {reason}")
    return True

def auto_morning_balance_check():
    """AUTO capture morning balance at 9:25 AM"""
    now = datetime.now()
    
    # Check if it's 9:25 AM
    if now.hour == 9 and now.minute == 25:
        state = load_state()
        
        if state['morning_balance'] is None:
            print("🌅 AUTO: Capturing morning balance at 9:25 AM...")
            balance = smart_get_balance()
            
            if balance:
                state['morning_balance'] = balance
                state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                state['current_balance'] = balance
                state['last_check'] = now.strftime('%H:%M:%S')
                save_state(state)
                
                print(f"💰 AUTO Morning Balance: ₹{balance:,.2f}")
                print(f"📊 AUTO 20% Loss Limit: ₹{state['max_loss_amount']:,.2f}")
            else:
                print("⏳ AUTO: Retrying balance fetch in 1 minute...")
                # Retry in 1 minute
                threading.Timer(60, auto_morning_balance_check).start()

def auto_real_time_monitor():
    """AUTO real-time monitoring loop"""
    state = load_state()
    now = datetime.now()
    
    print(f"⏰ AUTO Monitor: {now.strftime('%H:%M:%S')}")
    
    # Check trading hours
    trading_now = is_trading_time()
    
    # Auto stop trading outside hours
    if not trading_now and state['trading_allowed']:
        print("🕒 AUTO: Trading hours ended - Blocking trades")
        state['trading_allowed'] = False
        state['blocked_reason'] = 'Outside trading hours (9:25-15:00)'
        save_state(state)
        return
    
    # Only monitor during trading hours
    if trading_now:
        # Get current balance
        current_balance = smart_get_balance()
        
        if current_balance and state['morning_balance']:
            state['current_balance'] = current_balance
            state['last_check'] = now.strftime('%H:%M:%S')
            
            # Calculate loss
            loss = state['morning_balance'] - current_balance
            loss_percent = (loss / state['morning_balance']) * 100 if state['morning_balance'] > 0 else 0
            
            print(f"📈 AUTO P&L: ₹{current_balance:,.2f} | Loss: ₹{loss:,.2f} ({loss_percent:.1f}%)")
            
            # AUTO 20% LOSS CHECK
            if loss >= state['max_loss_amount'] and state['trading_allowed']:
                print(f"🚨 AUTO: 20% LOSS LIMIT HIT! ₹{loss:,.2f}")
                trigger_emergency_actions(f"20% Loss Limit: ₹{loss:,.2f}")
            
            # AUTO ORDER COUNT CHECK
            if state['order_count'] >= MAX_ORDERS_PER_DAY and state['trading_allowed']:
                print(f"🔢 AUTO: {MAX_ORDERS_PER_DAY} ORDERS LIMIT REACHED!")
                trigger_emergency_actions(f"{MAX_ORDERS_PER_DAY} Orders Limit")
        
        save_state(state)

def start_auto_scheduler():
    """Start all automatic schedulers"""
    scheduler = BackgroundScheduler()
    
    # Morning balance check at 9:25 AM
    scheduler.add_job(auto_morning_balance_check, 'cron', hour=9, minute=25)
    
    # Real-time monitor every 30 seconds
    scheduler.add_job(auto_real_time_monitor, 'interval', seconds=CHECK_INTERVAL)
    
    # Daily reset at 00:01 AM
    scheduler.add_job(
        lambda: save_state(load_state()),  # Force reset
        'cron', hour=0, minute=1
    )
    
    scheduler.start()
    print("🤖 AUTO Scheduler Started:")
    print("   • Morning balance @ 9:25 AM")
    print(f"   • Real-time monitor @ every {CHECK_INTERVAL} seconds")
    print("   • Daily reset @ 00:01 AM")
    
    return scheduler

# ==================== WEB ROUTES (For Monitoring) ====================

@app.route('/')
def dashboard():
    """AUTO System Dashboard"""
    state = load_state()
    trading_now = is_trading_time()
    
    status_color = "🟢" if state['trading_allowed'] else "🔴"
    time_status = "✅" if trading_now else "⏸️"
    
    return jsonify({
        'system': '🤖 FULLY AUTOMATIC DHAN RISK MANAGER',
        'version': 'AUTO-4.0',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        
        'auto_protection': {
            '20%_loss_limit': 'ACTIVE 🛡️',
            '10_orders_per_day': 'ACTIVE 🛡️',
            'trading_hours_9_25_15_00': 'ACTIVE 🛡️',
            'real_time_monitoring': 'ACTIVE 🛡️',
            'auto_emergency_actions': 'ACTIVE 🚨'
        },
        
        'current_status': {
            'trading_allowed': f"{status_color} {state['trading_allowed']}",
            'blocked_reason': state['blocked_reason'] or 'None',
            'trading_hours': f"{time_status} {trading_now}",
            'emergency_triggered': state['emergency_triggered']
        },
        
        'today_stats': {
            'date': state['date'],
            'morning_balance': f"₹{state['morning_balance']:,.2f}" if state['morning_balance'] else 'Not captured',
            'current_balance': f"₹{state['current_balance']:,.2f}" if state['current_balance'] else 'Not available',
            'max_loss_20%': f"₹{state['max_loss_amount']:,.2f}" if state['max_loss_amount'] else 'Not calculated',
            'orders_today': f"{state['order_count']}/{MAX_ORDERS_PER_DAY}",
            'last_check': state['last_check'] or 'Never'
        },
        
        'endpoints': {
            '/health': 'System health',
            '/force_balance': 'Manual balance fetch',
            '/emergency_stop': 'Trigger emergency',
            '/reset_day': 'Reset daily counts',
            '/simulate_order': 'Test order counting'
        }
    })

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'HEALTHY ✅',
        'auto_system': 'RUNNING 🤖',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/force_balance')
def force_balance():
    """Manually fetch balance"""
    balance = smart_get_balance()
    state = load_state()
    
    if balance:
        state['current_balance'] = balance
        if not state['morning_balance']:
            state['morning_balance'] = balance
            state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
        save_state(state)
    
    return jsonify({
        'balance': balance,
        'morning_balance': state['morning_balance'],
        'max_loss': state['max_loss_amount']
    })

@app.route('/emergency_stop')
def emergency_stop():
    """Manual emergency stop"""
    trigger_emergency_actions("Manual emergency stop")
    return jsonify({
        'status': 'EMERGENCY_EXECUTED',
        'trading_allowed': False,
        'message': 'All orders cancelled, positions exited, trading blocked'
    })

@app.route('/reset_day')
def reset_day():
    """Reset daily counts"""
    state = load_state()
    state.update({
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'emergency_triggered': False
    })
    save_state(state)
    
    return jsonify({
        'status': 'DAY_RESET',
        'order_count': 0,
        'trading_allowed': True
    })

@app.route('/simulate_order')
def simulate_order():
    """Simulate order for testing"""
    state = load_state()
    
    if not state['trading_allowed']:
        return jsonify({
            'error': 'Trading blocked',
            'reason': state['blocked_reason']
        })
    
    state['order_count'] += 1
    save_state(state)
    
    log_trade({
        'type': 'SIMULATED',
        'symbol': 'TEST',
        'quantity': 1,
        'price': 100,
        'side': 'BUY'
    })
    
    return jsonify({
        'status': 'ORDER_SIMULATED',
        'order_count': state['order_count'],
        'limit': MAX_ORDERS_PER_DAY,
        'remaining': MAX_ORDERS_PER_DAY - state['order_count'],
        'warning': 'BLOCK SOON' if state['order_count'] >= MAX_ORDERS_PER_DAY else 'OK'
    })

@app.route('/webhook/dhan_order', methods=['POST'])
def dhan_order_webhook():
    """Webhook for real order updates from Dhan"""
    try:
        order_data = request.json
        print(f"📥 AUTO: Order webhook received: {order_data}")
        
        # Log the trade
        log_trade(order_data)
        
        return jsonify({'status': 'ORDER_LOGGED'})
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'error': str(e)}), 400

# ==================== INITIALIZATION ====================

# Start auto scheduler
scheduler = start_auto_scheduler()

# Initial balance fetch
print("🔍 AUTO: Initial balance fetch...")
initial_balance = smart_get_balance()
if initial_balance:
    state = load_state()
    state['current_balance'] = initial_balance
    save_state(state)
    print(f"💰 Initial balance: ₹{initial_balance:,.2f}")

print("=" * 60)
print("🤖 FULLY AUTOMATIC DHAN RISK MANAGER v4.0")
print("=" * 60)
print("✅ AUTO PROTECTIONS ACTIVE:")
print(f"   • 20% Loss Limit: Auto detect & exit")
print(f"   • {MAX_ORDERS_PER_DAY} Orders/Day: Auto count & block")
print("   • Trading Hours 9:25-15:00: Auto enforce")
print("   • Morning Balance: Auto capture @ 9:25 AM")
print("   • Real-time Monitor: Auto every 30 seconds")
print("   • Emergency Actions: Auto cancel & exit")
print("=" * 60)
print("🌐 Dashboard: https://dhan-risk-manager.onrender.com/")
print("📊 Health: https://dhan-risk-manager.onrender.com/health")
print("=" * 60)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
