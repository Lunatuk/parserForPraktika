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
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

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
    chromedriver_path = 'C:\chromedriver-win64\chromedriver.exe'
    chrome_binary_path = 'C:\chrome-win64\chrome.exe'

    options = Options()
    options.binary_location = chrome_binary_path
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

    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)

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
    await update.message.reply_text('Этот бот создан Савельевым Иваном из группы БВТ2306 для летней практики.\nИспользуйте /search <запрос>, чтобы искать вакансии.')

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = ' '.join(context.args)
    logging.info(f"Получен запрос для поиска: {query}")
    if not query:
        await update.message.reply_text('Пожалуйста, введите запрос после команды /search.')
        return

    await update.message.reply_text(f'Ищу вакансии для: {query}')
    await run_parse_habr(query)
    await update.message.reply_text('Поиск завершен. Проверьте свою базу данных.')

async def run_parse_habr(query: str):
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor()
    
    await loop.run_in_executor(executor, parse_habr, query)

async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies ORDER BY id DESC LIMIT 5;")
        rows = cur.fetchall()
        for row in rows:
            await update.message.reply_text(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("recent", recent))

    application.run_polling()

if __name__ == '__main__':
    main()
