from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
from datetime import datetime
import requests
import os
import re

class UCShopHandler(BaseHTTPRequestHandler):
    
    def __init__(self, *args, **kwargs):
        self.bot_token = "8273045392:AAE63Q6oOOThCwUVOJ3mHlKRmCw-8aE_5jw"
        self.card_number = "2200 7020 0808 2617"
        self.shop_name = "Lezgin UC Shop"
        self.admin_chat_ids = [7254399392, 5265152558]
        self.init_database()
        super().__init__(*args, **kwargs)
    
    def init_database(self):
        try:
            self.conn = sqlite3.connect('uc_shop.db', check_same_thread=False)
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    player_id TEXT NOT NULL,
                    uc_amount INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    card_number TEXT NOT NULL
                )
            ''')
            self.conn.commit()
            print("✅ База данных готова")
        except Exception as e:
            print(f"❌ Ошибка БД: {e}")

    def do_GET(self):
        try:
            if self.path.startswith('/api/'):
                self.handle_api_request()
            else:
                self.serve_static_file()
        except Exception as e:
            print(f"❌ Ошибка в GET: {e}")
            self.send_error(500)

    def do_POST(self):
        try:
            if self.path == '/api/order':
                self.handle_order_request()
            elif self.path.startswith('/api/'):
                self.handle_api_request()
            else:
                self.send_error(404)
        except Exception as e:
            print(f"❌ Ошибка в POST: {e}")
            self.send_error(500)

    def handle_order_request(self):
        content_type = self.headers.get('Content-Type', '')
        
        if 'multipart/form-data' in content_type:
            self.create_order_with_receipt()
        else:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            self.create_simple_order(post_data)

    def parse_multipart(self, data, boundary):
        """Парсим multipart данные без cgi"""
        parts = data.split(b'--' + boundary)
        result = {}
        
        for part in parts:
            if b'Content-Disposition: form-data;' in part:
                # Ищем имя поля
                name_match = re.search(b'name="([^"]+)"', part)
                if name_match:
                    field_name = name_match.group(1).decode()
                    
                    # Ищем filename
                    filename_match = re.search(b'filename="([^"]+)"', part)
                    if filename_match:
                        # Это файл
                        filename = filename_match.group(1).decode()
                        file_data = part.split(b'\r\n\r\n')[1].split(b'\r\n--')[0]
                        result[field_name] = {'filename': filename, 'data': file_data}
                    else:
                        # Это текстовое поле
                        value = part.split(b'\r\n\r\n')[1].split(b'\r\n--')[0].decode()
                        result[field_name] = value
        
        return result

    def create_order_with_receipt(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Получаем boundary
            content_type = self.headers['Content-Type']
            boundary = content_type.split('boundary=')[1].encode()
            
            # Парсим multipart данные
            form_data = self.parse_multipart(post_data, boundary)
            
            player_id = form_data.get('playerId')
            uc_amount = form_data.get('uc')
            price = form_data.get('price')
            receipt_info = form_data.get('receipt')
            
            if not all([player_id, uc_amount, price]):
                self.send_error(400, "Missing required fields")
                return
            
            order_id = f"L{datetime.now().strftime('%H%M%S')}"
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Сохраняем в базу
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO orders (id, player_id, uc_amount, price, status, timestamp, card_number)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_id,
                player_id,
                int(uc_amount),
                int(price),
                'pending',
                timestamp,
                self.card_number
            ))
            self.conn.commit()
            
            print(f"✅ Заказ создан: {order_id}")
            
            # Отправляем в Telegram
            telegram_sent = False
            if receipt_info and 'data' in receipt_info:
                # Отправляем с чеком
                telegram_sent = self.send_telegram_with_receipt(
                    order_id, player_id, uc_amount, price, 
                    receipt_info['data'], receipt_info['filename']
                )
            else:
                # Отправляем без чека
                telegram_sent = self.send_telegram_notification(
                    order_id, player_id, uc_amount, price
                )
            
            response = {
                'success': True,
                'orderId': order_id,
                'telegram_sent': telegram_sent
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"❌ Ошибка создания заказа с чеком: {e}")
            self.send_error(500)

    def create_simple_order(self, post_data):
        try:
            order_data = json.loads(post_data.decode('utf-8'))
            
            order_id = f"L{datetime.now().strftime('%H%M%S')}"
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO orders (id, player_id, uc_amount, price, status, timestamp, card_number)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_id,
                order_data['playerId'],
                order_data['uc'],
                order_data['price'],
                'pending',
                timestamp,
                self.card_number
            ))
            self.conn.commit()
            
            print(f"✅ Заказ создан: {order_id}")
            
            telegram_sent = self.send_telegram_notification(
                order_id, order_data['playerId'], order_data['uc'], order_data['price']
            )
            
            response = {
                'success': True,
                'orderId': order_id,
                'telegram_sent': telegram_sent
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"❌ Ошибка создания заказа: {e}")
            self.send_error(500)

    def send_telegram_with_receipt(self, order_id, player_id, uc_amount, price, receipt_data, filename):
        try:
            message = f"""🆕 *НОВЫЙ ЗАКАЗ В {self.shop_name}*

🆔 *Заказ:* `{order_id}`
👤 *Player ID:* `{player_id}`
🎮 *UC:* {uc_amount}
💰 *Сумма:* {price} руб
💳 *Карта:* `{self.card_number}`
⏰ *Время:* {datetime.now().strftime('%H:%M:%S')}
📎 *Чек:* {filename}
📊 *Статус:* ⏳ Ожидает выполнения

⚡️ *СРОЧНО К ВЫПОЛНЕНИЮ!*"""
            
            return self.send_telegram_photo(receipt_data, filename, message)
        except Exception as e:
            print(f"❌ Ошибка отправки с чеком: {e}")
            return False

    def send_telegram_photo(self, photo_data, filename, caption):
        if not self.admin_chat_ids:
            return False
            
        try:
            success_count = 0
            for chat_id in self.admin_chat_ids:
                try:
                    files = {'photo': (filename, photo_data)}
                    response = requests.post(
                        f"https://api.telegram.org/bot{self.bot_token}/sendPhoto",
                        data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'},
                        files=files,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        success_count += 1
                        print(f"✅ Чек отправлен администратору")
                except Exception as e:
                    print(f"❌ Ошибка отправки фото: {e}")
            
            return success_count > 0
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            return False

    def send_telegram_notification(self, order_id, player_id, uc_amount, price):
        try:
            message = f"""🆕 *НОВЫЙ ЗАКАЗ В {self.shop_name}*

🆔 *Заказ:* `{order_id}`
👤 *Player ID:* `{player_id}`
🎮 *UC:* {uc_amount}
💰 *Сумма:* {price} руб
💳 *Карта:* `{self.card_number}`
⏰ *Время:* {datetime.now().strftime('%H:%M:%S')}
📊 *Статус:* ⏳ Ожидает выполнения

⚡️ *СРОЧНО К ВЫПОЛНЕНИЮ!*"""
            
            return self.send_telegram_message(message)
        except Exception as e:
            print(f"❌ Ошибка уведомления: {e}")
            return False

    def send_telegram_message(self, message):
        if not self.admin_chat_ids:
            return False
            
        try:
            success_count = 0
            for chat_id in self.admin_chat_ids:
                try:
                    response = requests.post(
                        f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                        json={
                            'chat_id': chat_id,
                            'text': message,
                            'parse_mode': 'Markdown'
                        },
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        success_count += 1
                        print(f"✅ Уведомление отправлено")
                except Exception as e:
                    print(f"❌ Ошибка отправки: {e}")
            
            return success_count > 0
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            return False

    def serve_static_file(self):
        if self.path == '/':
            self.path = '/index.html'
        
        try:
            file_path = '.' + self.path
            
            if os.path.exists(file_path) and os.path.isfile(file_path):
                if self.path.endswith('.html'):
                    mimetype = 'text/html'
                elif self.path.endswith('.css'):
                    mimetype = 'text/css'
                elif self.path.endswith('.js'):
                    mimetype = 'application/javascript'
                elif self.path.endswith('.png'):
                    mimetype = 'image/png'
                elif self.path.endswith('.jpg') or self.path.endswith('.jpeg'):
                    mimetype = 'image/jpeg'
                else:
                    mimetype = 'text/plain'
                
                with open(file_path, 'rb') as file:
                    self.send_response(200)
                    self.send_header('Content-type', mimetype)
                    self.end_headers()
                    self.wfile.write(file.read())
            else:
                self.send_error(404)
                
        except Exception as e:
            print(f"❌ Ошибка отдачи файла: {e}")
            self.send_error(500)

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def get_stats(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            total_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
            pending_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(price) FROM orders")
            total_revenue = cursor.fetchone()[0] or 0
            
            stats = {
                'total_orders': total_orders,
                'pending_orders': pending_orders,
                'total_revenue': total_revenue
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode())
        except Exception as e:
            print(f"❌ Ошибка статистики: {e}")
            self.send_error(500)

    def get_orders(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM orders ORDER BY timestamp DESC LIMIT 50")
            
            orders = []
            for row in cursor.fetchall():
                orders.append({
                    'id': row[0],
                    'playerId': row[1],
                    'uc': row[2],
                    'price': row[3],
                    'status': row[4],
                    'timestamp': row[5],
                    'cardNumber': row[6]
                })
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(orders).encode())
        except Exception as e:
            print(f"❌ Ошибка получения заказов: {e}")
            self.send_error(500)

    def get_prices(self):
        try:
            prices = {
                '60': 99,
                '120': 220,
                '325': 475,
                '385': 550,
                '660': 890,
                '720': 979,
                '985': 1300,
                '1320': 1850,
                '1800': 2200
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(prices).encode())
        except Exception as e:
            print(f"❌ Ошибка получения цен: {e}")
            self.send_error(500)

    def update_order(self, post_data):
        try:
            data = json.loads(post_data.decode('utf-8'))
            order_id = data['orderId']
            status = data['status']
            
            cursor = self.conn.cursor()
            cursor.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
            self.conn.commit()
            
            response = {'success': True}
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"❌ Ошибка обновления заказа: {e}")
            self.send_error(500)

    def handle_api_request(self):
        try:
            if self.path == '/api/stats':
                self.get_stats()
            elif self.path == '/api/orders':
                self.get_orders()
            elif self.path == '/api/prices':
                self.get_prices()
            elif self.path == '/api/update_order' and self.command == 'POST':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                self.update_order(post_data)
            else:
                self.send_error(404)
        except Exception as e:
            print(f"❌ Ошибка API: {e}")
            self.send_error(500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), UCShopHandler)
    print("=" * 50)
    print(f"🚀 LEZGIN UC SHOP ЗАПУЩЕН!")
    print(f"📡 Порт: {port}")
    print("💳 Карта: 2200 7020 0808 2617")
    print("👥 Админы: @LEZGImaga05, @rrrrnn05")
    print("=" * 50)
    server.serve_forever()

if __name__ == '__main__':
    run_server()
