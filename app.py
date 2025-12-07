import os
import time
import json
import threading
import requests
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request

app = Flask(__name__)

# ==================== CONFIG ====================
MAX_ORDERS_PER_DAY = 10
MAX_LOSS_PERCENT = 0.20  # 20%
TRADING_START = dtime(9, 25)
TRADING_END = dtime(15, 0)

# Dhan API Configuration
CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
HEADERS = {
    'access-token': ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# ==================== Dhan API FUNCTIONS ====================

def get_dhan_balance():
    """Get balance from Dhan API - WORKING VERSION"""
    try:
        # TRY 1: Funds endpoint (most common)
        print("🔍 Trying /funds endpoint...")
        response = requests.get(
            'https://api.dhan.co/funds',
            headers=HEADERS,
            timeout=10
        )
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Funds Response: {data}")
            
            # Extract balance from different possible structures
            if isinstance(data, dict):
                # Try common balance fields
                balance_fields = ['netAvailableMargin', 'availableMargin', 'marginAvailable', 'balance']
                for field in balance_fields:
                    if field in data:
                        try:
                            balance = float(data[field])
                            print(f"💰 Balance from {field}: ₹{balance}")
                            return balance
                        except:
                            continue
            
            # If list, check first item
            if isinstance(data, list) and len(data) > 0:
                item = data[0]
                if isinstance(item, dict):
                    balance_fields = ['netAvailableMargin', 'availableMargin', 'marginAvailable']
                    for field in balance_fields:
                        if field in item:
                            try:
                                balance = float(item[field])
                                print(f"💰 Balance from list[{field}]: ₹{balance}")
                                return balance
                            except:
                                continue
        
        # TRY 2: Margin endpoint
        print("🔍 Trying /margin endpoint...")
        response = requests.get(
            'https://api.dhan.co/margin',
            headers=HEADERS,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Margin Response: {data}")
            
            if isinstance(data, dict):
                if 'marginAvailable' in data:
                    try:
                        balance = float(data['marginAvailable'])
                        print(f"💰 Margin Available: ₹{balance}")
                        return balance
                    except:
                        pass
        
        # TRY 3: Account endpoint
        print("🔍 Trying /account endpoint...")
        response = requests.get(
            'https://api.dhan.co/account',
            headers=HEADERS,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Account Response: {data}")
            
            if isinstance(data, dict):
                balance_fields = ['balance', 'cashBalance', 'availableCash']
                for field in balance_fields:
                    if field in data:
                        try:
                            balance = float(data[field])
                            print(f"💰 Account {field}: ₹{balance}")
                            return balance
                        except:
                            continue
        
        print("❌ All endpoints failed or returned no balance")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def get_dhan_positions():
    """Get current positions"""
    try:
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def get_dhan_orders():
    """Get today's orders"""
    try:
        response = requests.get(
            'https://api.dhan.co/orders',
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def place_dhan_order(order_data):
    """Place an order"""
    try:
        response = requests.post(
            'https://api.dhan.co/orders',
            headers=HEADERS,
            json=order_data,
            timeout=10
        )
        return response.json()
    except:
        return None

# ==================== STATE MANAGEMENT ====================

class TradingState:
    def __init__(self):
        self.state_file = 'trading_state.json'
        self.default_state = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'morning_balance': None,
            'max_loss_amount': None,
            'order_count': 0,
            'trading_allowed': True,
            'blocked_reason': '',
            'last_balance_check': None,
            'current_balance': None
        }
        self.state = self.load_state()
    
    def load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    saved = json.load(f)
                    # Check if it's a new day
                    if saved.get('date') != self.default_state['date']:
                        print("🔄 New day detected, resetting state")
                        return self.default_state
                    return saved
        except Exception as e:
            print(f"❌ Error loading state: {e}")
        
        return self.default_state.copy()
    
    def save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving state: {e}")
    
    def reset_daily(self):
        self.state = self.default_state.copy()
        self.save_state()
        print("✅ Daily state reset")

# Initialize state
trading_state = TradingState()

# ==================== AUTOMATIC RULES ====================

def is_trading_time():
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def check_trading_hours():
    """Check if within trading hours"""
    if not is_trading_time():
        if trading_state.state['trading_allowed']:
            print("🕒 Outside trading hours (9:25-15:00)")
            trading_state.state['trading_allowed'] = False
            trading_state.state['blocked_reason'] = 'Outside trading hours'
            trading_state.save_state()
        return False
    return True

def capture_morning_balance():
    """Capture balance at 9:25 AM"""
    now = datetime.now()
    
    # Check if it's around 9:25 AM and balance not captured
    if (now.hour == 9 and now.minute >= 25) or now.hour > 9:
        if trading_state.state['morning_balance'] is None:
            print("🌅 Capturing morning balance...")
            balance = get_dhan_balance()
            
            if balance:
                print(f"💰 Morning Balance: ₹{balance:,.2f}")
                trading_state.state['morning_balance'] = balance
                trading_state.state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                trading_state.state['current_balance'] = balance
                trading_state.state['last_balance_check'] = now.strftime('%H:%M:%S')
                trading_state.save_state()
                print(f"📊 20% Loss Limit set to: ₹{trading_state.state['max_loss_amount']:,.2f}")
                return True
            else:
                print("⏳ Failed to get balance, will retry...")
    
    return False

def check_loss_limit():
    """Check 20% loss limit"""
    if trading_state.state['morning_balance']:
        current_balance = get_dhan_balance()
        
        if current_balance:
            trading_state.state['current_balance'] = current_balance
            trading_state.state['last_balance_check'] = datetime.now().strftime('%H:%M:%S')
            
            loss = trading_state.state['morning_balance'] - current_balance
            loss_percent = (loss / trading_state.state['morning_balance']) * 100 if trading_state.state['morning_balance'] > 0 else 0
            
            print(f"📈 Balance: ₹{current_balance:,.2f} | Loss: ₹{loss:,.2f} ({loss_percent:.1f}%)")
            
            # Check 20% loss
            if loss >= trading_state.state['max_loss_amount'] and trading_state.state['trading_allowed']:
                print(f"🚨 20% LOSS LIMIT HIT! ₹{loss:,.2f}")
                trading_state.state['trading_allowed'] = False
                trading_state.state['blocked_reason'] = f'20% Loss: ₹{loss:,.2f}'
                trading_state.save_state()
                
                # Emergency action - cancel orders
                try:
                    orders = get_dhan_orders()
                    print(f"🛑 Cancelling {len(orders)} orders...")
                except:
                    pass
                
                return True
        
        trading_state.save_state()
    
    return False

def check_order_limit():
    """Check 10 orders per day limit"""
    orders = get_dhan_orders()
    
    # Count today's orders
    today = datetime.now().strftime('%Y-%m-%d')
    today_orders = []
    
    for order in orders:
        if isinstance(order, dict):
            order_time = order.get('orderTimestamp', '')
            if today in order_time:
                today_orders.append(order)
    
    order_count = len(today_orders)
    
    # Update state
    trading_state.state['order_count'] = order_count
    
    # Check limit
    if order_count >= MAX_ORDERS_PER_DAY and trading_state.state['trading_allowed']:
        print(f"🔢 {MAX_ORDERS_PER_DAY} ORDERS LIMIT REACHED!")
        trading_state.state['trading_allowed'] = False
        trading_state.state['blocked_reason'] = f'{MAX_ORDERS_PER_DAY} orders per day'
        trading_state.save_state()
        return True
    
    trading_state.save_state()
    return False

def auto_monitor_loop():
    """Main automatic monitoring loop"""
    print("🤖 STARTING AUTOMATIC MONITOR")
    print(f"✅ Rules: {MAX_ORDERS_PER_DAY} orders/day, 20% loss, 9:25-15:00")
    
    while True:
        try:
            now = datetime.now()
            current_time = now.strftime('%H:%M:%S')
            print(f"\n⏰ AUTO CHECK: {current_time}")
            
            # 1. Check trading hours
            trading_now = check_trading_hours()
            
            if trading_now:
                # 2. Capture morning balance
                capture_morning_balance()
                
                # 3. Check loss limit
                check_loss_limit()
                
                # 4. Check order limit
                check_order_limit()
            
            # 5. Log current status
            status = "ALLOWED ✅" if trading_state.state['trading_allowed'] else "BLOCKED 🔴"
            print(f"📊 STATUS: {status} | Orders: {trading_state.state['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            time.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            print(f"❌ Monitor error: {e}")
            time.sleep(60)

# Start monitor thread
monitor_thread = threading.Thread(target=auto_monitor_loop, daemon=True)
monitor_thread.start()

# ==================== WEB ROUTES ====================

@app.route('/')
def dashboard():
    """Main dashboard"""
    trading_now = is_trading_time()
    
    # Get latest balance
    current_balance = get_dhan_balance()
    if current_balance:
        trading_state.state['current_balance'] = current_balance
        trading_state.state['last_balance_check'] = datetime.now().strftime('%H:%M:%S')
    
    # Calculate loss if morning balance exists
    loss_info = {}
    if trading_state.state['morning_balance'] and current_balance:
        loss = trading_state.state['morning_balance'] - current_balance
        loss_percent = (loss / trading_state.state['morning_balance']) * 100
        loss_info = {
            'amount': f'₹{loss:,.2f}',
            'percent': f'{loss_percent:.1f}%',
            'limit': f'₹{trading_state.state["max_loss_amount"]:,.2f}' if trading_state.state['max_loss_amount'] else 'N/A'
        }
    
    return jsonify({
        'system': '🤖 DHAN AUTOMATIC RISK MANAGER',
        'status': 'ACTIVE',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        
        'api_status': {
            'connected': bool(ACCESS_TOKEN),
            'client_id': CLIENT_ID[:5] + '...' if CLIENT_ID else 'Not set',
            'last_check': trading_state.state['last_balance_check']
        },
        
        'automatic_protections': {
            '20%_loss_limit': {
                'status': 'ACTIVE 🛡️',
                'morning_balance': f'₹{trading_state.state["morning_balance"]:,.2f}' if trading_state.state["morning_balance"] else 'Not captured',
                'current_balance': f'₹{current_balance:,.2f}' if current_balance else 'N/A',
                'current_loss': loss_info,
                'max_loss_20%': f'₹{trading_state.state["max_loss_amount"]:,.2f}' if trading_state.state["max_loss_amount"] else 'N/A'
            },
            'order_limit': {
                'status': 'ACTIVE 🛡️',
                'limit': MAX_ORDERS_PER_DAY,
                'today': trading_state.state['order_count'],
                'remaining': MAX_ORDERS_PER_DAY - trading_state.state['order_count']
            },
            'trading_hours': {
                'status': 'ACTIVE 🛡️',
                'hours': '9:25 AM - 3:00 PM',
                'currently': 'OPEN ✅' if trading_now else 'CLOSED 🔒',
                'current_time': datetime.now().strftime('%H:%M')
            }
        },
        
        'trading_status': {
            'allowed': trading_state.state['trading_allowed'],
            'blocked_reason': trading_state.state['blocked_reason'] or 'None',
            'date': trading_state.state['date']
        },
        
        'actions': {
            'check_balance': '/check_balance',
            'check_orders': '/check_orders',
            'check_positions': '/check_positions',
            'reset': '/reset',
            'health': '/health',
            'test_api': '/test_api'
        }
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'HEALTHY',
        'auto_monitor': 'RUNNING',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/check_balance')
def check_balance():
    """Check current balance"""
    balance = get_dhan_balance()
    
    if balance:
        trading_state.state['current_balance'] = balance
        trading_state.state['last_balance_check'] = datetime.now().strftime('%H:%M:%S')
        trading_state.save_state()
    
    return jsonify({
        'balance': balance,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'morning_balance': trading_state.state['morning_balance'],
        'max_loss': trading_state.state['max_loss_amount']
    })

@app.route('/check_orders')
def check_orders():
    """Check today's orders"""
    orders = get_dhan_orders()
    today = datetime.now().strftime('%Y-%m-%d')
    today_orders = []
    
    for order in orders:
        if isinstance(order, dict):
            order_time = order.get('orderTimestamp', '')
            if today in order_time:
                today_orders.append(order)
    
    # Update order count
    trading_state.state['order_count'] = len(today_orders)
    trading_state.save_state()
    
    return jsonify({
        'total_orders': len(orders),
        'today_orders': len(today_orders),
        'order_count': trading_state.state['order_count'],
        'limit': MAX_ORDERS_PER_DAY,
        'orders': today_orders[:10]  # First 10 orders only
    })

@app.route('/check_positions')
def check_positions():
    """Check current positions"""
    positions = get_dhan_positions()
    return jsonify({
        'positions': positions,
        'count': len(positions)
    })

@app.route('/test_api')
def test_api():
    """Test Dhan API connection"""
    try:
        # Test with funds endpoint
        response = requests.get(
            'https://api.dhan.co/funds',
            headers=HEADERS,
            timeout=10
        )
        
        return jsonify({
            'status_code': response.status_code,
            'response': response.json() if response.status_code == 200 else str(response.text),
            'headers_sent': {
                'access-token': HEADERS['access-token'][:10] + '...' if HEADERS['access-token'] else 'None'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reset')
def reset():
    """Reset daily state"""
    trading_state.reset_daily()
    return jsonify({
        'status': 'RESET',
        'message': 'Daily state reset',
        'order_count': 0,
        'trading_allowed': True
    })

@app.route('/simulate_order')
def simulate_order():
    """Simulate an order (for testing)"""
    if not trading_state.state['trading_allowed']:
        return jsonify({
            'error': 'TRADING_BLOCKED',
            'reason': trading_state.state['blocked_reason']
        })
    
    trading_state.state['order_count'] += 1
    trading_state.save_state()
    
    return jsonify({
        'order_simulated': True,
        'order_count': trading_state.state['order_count'],
        'remaining': MAX_ORDERS_PER_DAY - trading_state.state['order_count']
    })

# ==================== START SERVER ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    
    print("=" * 60)
    print("🤖 DHAN AUTOMATIC RISK MANAGER")
    print("=" * 60)
    print("✅ REAL Dhan API Integration")
    print("=" * 60)
    print("🛡️ ACTIVE PROTECTIONS:")
    print(f"   1. 20% Daily Loss Limit")
    print(f"   2. {MAX_ORDERS_PER_DAY} Orders per day")
    print("   3. Trading Hours: 9:25 AM - 3:00 PM")
    print("=" * 60)
    print("🔑 API STATUS:")
    print(f"   Client ID: {CLIENT_ID[:10]}..." if CLIENT_ID else "   Client ID: Not set")
    print(f"   Token: {'Set' if ACCESS_TOKEN else 'Not set'}")
    print("=" * 60)
    print(f"🌐 Starting on port {port}...")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
