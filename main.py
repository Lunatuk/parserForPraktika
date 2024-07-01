import os
import psycopg2
import time
import dotenv
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import asyncio
import concurrent.futures
import random

dotenv.load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('TELEGRAM_TOKEN')

def connect_db():
    dbname = os.environ.get('DB_NAME')
    dbuser = os.environ.get('DB_USER')
    dbpassword = os.environ.get('DB_PASSWORD')
    dbhost = os.environ.get('DB_HOST')
    dbport = os.environ.get('DB_PORT')

    conn = psycopg2.connect(
        dbname=dbname,
        user=dbuser,
        password=dbpassword,
        host=dbhost,
        port=dbport
    )
    return conn

def insert_vacancy(conn, company, title, meta_info, salary, skills, link):
    with conn.cursor() as cur:
        cur.execute("""
        INSERT INTO vacancies (company, vacancy, location, salary, skills, link)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
        """, (company, title, meta_info, salary, skills, link))
        conn.commit()
        return cur.fetchone()[0]

def parse_habr(query):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-webgl')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=WebRtcHideLocalIpsWithMdns,WebContentsDelegate::CheckMediaAccessPermission')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    options.add_argument('--remote-debugging-port=9222')
    options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
    options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_experimental_option('prefs', {
        'profile.managed_default_content_settings.images': 2,
        'disk-cache-size': 4096
    })

    driver = webdriver.Chrome(options=options)

    conn = connect_db()

    try:
        driver.get('https://career.habr.com')

        search_input = driver.find_element(By.CSS_SELECTOR, '.l-page-title__input')
        search_input.send_keys(query)
        search_input.send_keys(Keys.RETURN)

        time.sleep(1)

        while True:
            vacancies = driver.find_elements(By.CLASS_NAME, 'vacancy-card__info')
            for vacancy in vacancies:
                try:
                    company_element = vacancy.find_element(By.CLASS_NAME, 'vacancy-card__company-title')
                    company = company_element.text
                except NoSuchElementException:
                    company = 'Компания не указана'

                title_element = vacancy.find_element(By.CLASS_NAME, 'vacancy-card__title')
                title = title_element.text
                link = title_element.find_element(By.TAG_NAME, 'a').get_attribute('href')

                try:
                    meta_element = vacancy.find_element(By.CLASS_NAME, 'vacancy-card__meta')
                    meta_info = meta_element.text
                except NoSuchElementException:
                    meta_info = 'Местоположение не указано'

                try:
                    salary = vacancy.find_element(By.CLASS_NAME, 'vacancy-card__salary').text
                except NoSuchElementException:
                    salary = 'ЗП не указана'

                try:
                    skills = vacancy.find_element(By.CLASS_NAME, 'vacancy-card__skills').text
                except NoSuchElementException:
                    skills = 'Скиллы не указаны'

                vacancy_id = insert_vacancy(conn, company, title, meta_info, salary, skills, link)

                print(f'Компания: {company}\nВакансия: {title}\nСсылка: {link}\nМестоположение и режим работы: {meta_info}\nЗарплата: {salary}\nСкиллы: {skills}')

            try:
                next_button = driver.find_element(By.CSS_SELECTOR, 'a.button-comp--appearance-pagination-button[rel="next"]')
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                time.sleep(1)
                
                for _ in range(3):
                    try:
                        driver.execute_script("arguments[0].click();", next_button)
                        break
                    except StaleElementReferenceException:
                        next_button = driver.find_element(By.CSS_SELECTOR, 'a.button-comp--appearance-pagination-button[rel="next"]')
                        time.sleep(1)
                else:
                    break
                
                time.sleep(1)
            except (NoSuchElementException, ElementClickInterceptedException):
                break

    finally:
        driver.quit()
        conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Используйте /search <запрос>, чтобы искать вакансии.')

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = ' '.join(context.args)
    logging.info(f"Получен запрос для поиска: {query}")
    if not query:
        await update.message.reply_text('Пожалуйста, введите запрос после команды /search.')
        return

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vacancies;")
        initial_count = cur.fetchone()[0]
    conn.close()

    await update.message.reply_text(f'Ищу вакансии для: {query}')
    await run_parse_habr(query)
    await update.message.reply_text('Поиск завершен. Проверьте свою базу данных.')

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies WHERE id > %s ORDER BY id LIMIT 5;", (initial_count,))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text('Новые вакансии не найдены.')
    else:
        await update.message.reply_text('Ниже представлены 5 новых вакансий:')
        for row in rows:
            await update.message.reply_text(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

async def run_parse_habr(query: str):
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor()
    await loop.run_in_executor(executor, parse_habr, query)

async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies ORDER BY RANDOM() LIMIT 5;")
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text('Вакансии не найдены.')
    else:
        for row in rows:
            await update.message.reply_text(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

async def count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vacancies;")
        count = cur.fetchone()[0]
    conn.close()
    await update.message.reply_text(f'Общее количество вакансий в базе данных: {count}')

async def grafic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Неполный рабочий день", callback_data='part_time'),
            InlineKeyboardButton("Полный рабочий день", callback_data='full_time')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Выберите график работы:', reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    query_data = query.data

    conn = connect_db()
    with conn.cursor() as cur:
        if query_data == 'part_time':
            cur.execute("SELECT COUNT(*)FROM vacancies WHERE location ILIKE '%Неполный рабочий день%';")
        elif query_data == 'full_time':
            cur.execute("SELECT COUNT(*) FROM vacancies WHERE location ILIKE '%Полный рабочий день%';")
        count = cur.fetchone()[0]
    conn.close()

    await query.answer()
    await query.edit_message_text(text=f'Количество вакансий с графиком "{query_data}": {count}')

async def search_by_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    company_name = ' '.join(context.args)
    logging.info(f"Получен запрос для поиска по компании: {company_name}")
    if not company_name:
        await update.message.reply_text('Пожалуйста, введите название компании после команды /search_company.')
        return

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies WHERE company ILIKE %s ORDER BY RANDOM() LIMIT 5;", (f"%{company_name}%",))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f'Вакансии компании "{company_name}" не найдены.')
    else:
        for row in rows:
            await update.message.reply_text(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

async def search_by_vacancy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    vacancy_query = ' '.join(context.args)
    logging.info(f"Получен запрос для поиска по вакансии: {vacancy_query}")
    if not vacancy_query:
        await update.message.reply_text('Пожалуйста, введите название вакансии после команды /search_vacancy.')
        return

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies WHERE vacancy ILIKE %s ORDER BY RANDOM() LIMIT 5;", (f"%{vacancy_query}%",))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f'Вакансии по запросу "{vacancy_query}" не найдены.')
    else:
        for row in rows:
            await update.message.reply_text(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("recent", recent))
    application.add_handler(CommandHandler("count", count))
    application.add_handler(CommandHandler("grafic", grafic))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("search_company", search_by_company))
    application.add_handler(CommandHandler("search_vacancy", search_by_vacancy))

    application.run_polling()

if __name__ == '__main__':
    main()
