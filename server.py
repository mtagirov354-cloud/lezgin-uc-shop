from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
from datetime import datetime
import requests
import os
import cgi
import io

class UCShopHandler(BaseHTTPRequestHandler):
    
    def __init__(self, *args, **kwargs):
        # Сначала определяем атрибуты, потом вызываем super()
        self.bot_token = "8273045392:AAE63Q6oOOThCwUVOJ3mHlKRmCw-8aE_5jw"
        self.card_number = "2200 7020 0808 2617"
        self.shop_name = "Lezgin UC Shop"
        self.admin_usernames = ['LEZGImaga05', 'rrrrnn05']  # ОБА АДМИНА ДОБАВЛЕНЫ
        
        # Теперь инициализируем базу и загружаем chat_id
        self.init_database()
        self.admin_chat_ids = self.load_chat_ids()
        
        # Потом вызываем родительский конструктор
        super().__init__(*args, **kwargs)
        
        # И отправляем стартовое сообщение
        self.send_startup_message()
    
    def load_chat_ids(self):
        """Автоматически загружаем chat_id из обновлений бота"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok') and result['result']:
                    chat_ids = []
                    for update in result['result']:
                        if 'message' in update:
                            chat_id = update['message']['chat']['id']
                            username = update['message']['chat'].get('username', '').lower()
                            # Добавляем чат если пользователь админ или если это тестовый режим
                            if username in [admin.lower() for admin in self.admin_usernames] or not self.admin_usernames:
                                if chat_id not in chat_ids:
                                    chat_ids.append(chat_id)
                                    print(f"✅ Найден администратор: {username} (ID: {chat_id})")
                    
                    if chat_ids:
                        print(f"✅ Автоматически загружено {len(chat_ids)} chat_id администраторов")
                        return chat_ids
                    else:
                        print("ℹ️  Chat_id администраторов не найдены. Напишите боту в Telegram.")
                        return []
                else:
                    print("ℹ️  Нет обновлений. Напишите боту в Telegram.")
                    return []
            else:
                print(f"❌ Ошибка загрузки chat_id: {response.text}")
                return []
                
        except Exception as e:
            print(f"❌ Ошибка загрузки chat_id: {e}")
            return []
    
    def send_startup_message(self):
        """Отправляем сообщение о запуске сервера"""
        if not self.admin_chat_ids:
            print("❌ Не могу отправить стартовое сообщение - нет chat_id")
            return
            
        try:
            message = f"""🚀 *{self.shop_name} запущен!*

✅ Сервер готов к работе
👥 Администраторы: @LEZGImaga05, @rrrrnn05
📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}

Ожидаю новые заказы с чеками... 🎮"""

            success = self.send_telegram_message(message)
            
            if success:
                print("✅ Стартовое сообщение отправлено администраторам")
            else:
                print("❌ Не удалось отправить стартовое сообщение")
                
        except Exception as e:
            print(f"❌ Ошибка отправки стартового сообщения: {e}")
    
    def init_database(self):
        """Инициализация базы данных"""
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
            print("✅ База данных инициализирована")
        except Exception as e:
            print(f"❌ Ошибка инициализации БД: {e}")

    # ОСТАЛЬНЫЕ МЕТОДЫ БЕЗ ИЗМЕНЕНИЙ (do_GET, do_POST, handle_order_request, и т.д.)
    
    def do_GET(self):
        """Обработка GET запросов"""
        try:
            if self.path.startswith('/api/'):
                self.handle_api_request()
            else:
                self.serve_static_file()
        except Exception as e:
            print(f"❌ Ошибка в GET {self.path}: {e}")
            self.send_error(500, f"Server error: {str(e)}")
    
    def do_POST(self):
        """Обработка POST запросов"""
        try:
            if self.path.startswith('/api/order'):
                self.handle_order_request()
            elif self.path.startswith('/api/'):
                self.handle_api_request()
            else:
                self.send_error(404)
        except Exception as e:
            print(f"❌ Ошибка в POST {self.path}: {e}")
            self.send_error(500, f"Server error: {str(e)}")
    
    def handle_order_request(self):
        """Обработка запроса на создание заказа"""
        content_type = self.headers.get('Content-Type', '')
        
        if 'multipart/form-data' in content_type:
            self.create_order_with_receipt()
        else:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            self.create_order(post_data)
    
    def create_order_with_receipt(self):
        """Создание заказа с чеком"""
        try:
            # Используем cgi для парсинга multipart данных
            content_type = self.headers['Content-Type']
            fs = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type}
            )
            
            # Получаем текстовые поля
            player_id = fs.getvalue('playerId')
            uc_amount = fs.getvalue('uc')
            price = fs.getvalue('price')
            
            if not all([player_id, uc_amount, price]):
                self.send_error(400, "Missing required fields")
                return
            
            # Получаем файл
            receipt_item = fs['receipt']
            if not receipt_item.filename:
                self.send_error(400, "No file uploaded")
                return
            
            receipt_data = receipt_item.file.read()
            filename = receipt_item.filename
            
            print(f"✅ Получен файл: {filename}, размер: {len(receipt_data)} байт")
            
            # Создаем заказ в БД
            order_id = f"L{datetime.now().strftime('%H%M%S')}"
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
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
            
            # Отправляем уведомление в Telegram с чеком
            telegram_sent = self.send_telegram_notification_with_receipt(
                order_id, player_id, uc_amount, price, receipt_data, filename
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
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Error creating order: {str(e)}")
    
    def create_order(self, post_data):
        """Создание заказа без чека (для совместимости)"""
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
            
            telegram_sent = self.send_telegram_notification(order_id, order_data)
            
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
            self.send_error(500, f"Error creating order: {str(e)}")
    
    def send_telegram_notification_with_receipt(self, order_id, player_id, uc_amount, price, receipt_data, filename):
        """Отправка уведомления в Telegram с чеком"""
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
            print(f"❌ Ошибка создания уведомления с чеком: {e}")
            return False
    
    def send_telegram_photo(self, photo_data, filename, caption):
        """Отправка фото в Telegram"""
        if not self.admin_chat_ids:
            print("❌ Нет chat_id для отправки сообщений")
            return False
            
        try:
            success_count = 0
            
            for chat_id in self.admin_chat_ids:
                try:
                    # Создаем BytesIO объект для отправки
                    files = {'photo': (filename, photo_data)}
                    
                    response = requests.post(
                        f"https://api.telegram.org/bot{self.bot_token}/sendPhoto",
                        data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'},
                        files=files,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('ok'):
                            success_count += 1
                            print(f"✅ Чек отправлен администратору (ID: {chat_id})")
                        else:
                            print(f"❌ Ошибка Telegram API для ID {chat_id}: {result.get('description')}")
                    else:
                        print(f"❌ HTTP ошибка для ID {chat_id}: {response.text}")
                        
                except requests.exceptions.Timeout:
                    print(f"⏰ Таймаут при отправке чека администратору (ID: {chat_id})")
                except Exception as e:
                    print(f"❌ Ошибка отправки чека администратору (ID: {chat_id}): {e}")
            
            return success_count > 0
        except Exception as e:
            print(f"❌ Критическая ошибка отправки чека в Telegram: {e}")
            return False
    
    def send_telegram_notification(self, order_id, order_data):
        """Отправка уведомления в Telegram без чека"""
        try:
            message = f"""🆕 *НОВЫЙ ЗАКАЗ В {self.shop_name}*

🆔 *Заказ:* `{order_id}`
👤 *Player ID:* `{order_data['playerId']}`
🎮 *UC:* {order_data['uc']}
💰 *Сумма:* {order_data['price']} руб
💳 *Карта:* `{self.card_number}`
⏰ *Время:* {datetime.now().strftime('%H:%M:%S')}
📊 *Статус:* ⏳ Ожидает выполнения

⚡️ *СРОЧНО К ВЫПОЛНЕНИЮ!*"""
            
            return self.send_telegram_message(message)
        except Exception as e:
            print(f"❌ Ошибка создания уведомления: {e}")
            return False
    
    def send_telegram_message(self, message):
        """Отправка сообщения в Telegram"""
        if not self.admin_chat_ids:
            print("❌ Нет chat_id для отправки сообщений")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            success_count = 0
            for chat_id in self.admin_chat_ids:
                try:
                    response = requests.post(url, json={
                        'chat_id': chat_id,
                        'text': message,
                        'parse_mode': 'Markdown'
                    }, timeout=10)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('ok'):
                            success_count += 1
                            print(f"✅ Уведомление отправлено администратору (ID: {chat_id})")
                        else:
                            error_desc = result.get('description', 'Unknown error')
                            print(f"❌ Ошибка для администратора (ID: {chat_id}): {error_desc}")
                    else:
                        print(f"❌ HTTP ошибка для администратора (ID: {chat_id}): {response.text}")
                        
                except requests.exceptions.Timeout:
                    print(f"⏰ Таймаут при отправке администратору (ID: {chat_id})")
                except Exception as e:
                    print(f"❌ Ошибка отправки администратору (ID: {chat_id}): {e}")
            
            return success_count > 0
        except Exception as e:
            print(f"❌ Критическая ошибка отправки в Telegram: {e}")
            return False

    def serve_static_file(self):
        """Обслуживание статических файлов"""
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
            print(f"❌ Ошибка отдачи файла {self.path}: {e}")
            self.send_error(500, f"File error: {str(e)}")
    
    def send_cors_headers(self):
        """Отправка CORS заголовков"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def get_stats(self):
        """Получение статистики"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM orders")
            total_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
            pending_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(price) FROM orders")
            total_revenue = cursor.fetchone()[0] or 0
            
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("SELECT SUM(price) FROM orders WHERE date(timestamp) = ?", (today,))
            today_revenue = cursor.fetchone()[0] or 0
            
            stats = {
                'total_orders': total_orders,
                'pending_orders': pending_orders,
                'total_revenue': total_revenue,
                'today_revenue': today_revenue
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode())
        except Exception as e:
            print(f"❌ Ошибка получения статистики: {e}")
            self.send_error(500, "Error getting stats")
    
    def get_orders(self):
        """Получение списка заказов"""
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
            self.send_error(500, "Error getting orders")
    
    def get_prices(self):
        """Получение цен"""
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
            self.send_error(500, "Error getting prices")
    
    def update_order(self, post_data):
        """Обновление статуса заказа"""
        try:
            data = json.loads(post_data.decode('utf-8'))
            order_id = data['orderId']
            status = data['status']
            
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE orders SET status = ? WHERE id = ?
            ''', (status, order_id))
            self.conn.commit()
            
            print(f"✅ Статус заказа {order_id} обновлен на: {status}")
            
            if status == 'completed':
                self.send_telegram_update(order_id, '✅ ЗАКАЗ ВЫПОЛНЕН')
            
            response = {'success': True}
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"❌ Ошибка обновления заказа: {e}")
            self.send_error(500, f"Error updating order: {str(e)}")
    
    def send_telegram_update(self, order_id, text):
        """Отправка обновления в Telegram"""
        try:
            message = f"{text} {order_id}\n🏪 {self.shop_name}\n👥 Админы: @LEZGImaga05, @rrrrnn05"
            self.send_telegram_message(message)
        except Exception as e:
            print(f"❌ Ошибка отправки обновления: {e}")

    def handle_api_request(self):
        """Обработка API запросов"""
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
            print(f"❌ Ошибка обработки API {self.path}: {e}")
            self.send_error(500, f"API error: {str(e)}")
    
    def do_OPTIONS(self):
        """Обработка CORS preflight"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

def run_server():
    port = 8000
    server = HTTPServer(('localhost', port), UCShopHandler)
    
    print("=" * 60)
    print("🚀 LEZGIN UC SHOP ЗАПУЩЕН!")
    print("=" * 60)
    print(f"📡 Адрес: http://localhost:{port}")
    print("💳 Карта: 2200 7020 0808 2617")
    print("👥 Администраторы: @LEZGImaga05, @rrrrnn05")
    print("🌐 Сервер автоматически загружает chat_id администраторов")
    print("📎 Поддержка загрузки чеков: ВКЛЮЧЕНА")
    print("🖼️  Отправка фото в Telegram: ВКЛЮЧЕНА")
    print("🤖 Telegram бот готов к уведомлениям с чеками")
    print("\n💡 Откройте в браузере: http://localhost:8000")
    print("=" * 60)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен пользователем")
    except Exception as e:
        print(f"\n💥 Критическая ошибка сервера: {e}")
    finally:
        try:
            server.server_close()
            print("✅ Ресурсы сервера освобождены")
        except:
            pass

if __name__ == '__main__':
    run_server()
