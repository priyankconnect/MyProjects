import os
import re
import time
import requests
from io import BytesIO
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from PIL import Image

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


URL = "https://indiehaat.com/collections/maheshwari-silk-sarees"
TARGET_PRODUCTS = 50
OUT_DIR = "indiehaat_images_jpeg"
SITE_NAME = "indiehaat"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ImageScraper/1.0)"}


def normalize_url(u: str) -> str:
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    return u


def pick_best_from_bgset(bgset: str) -> str:
    """
    Example item:
    //..._750x.jpg?v=... 750w 1000h
    Pick the largest width candidate.
    """
    if not bgset:
        return ""

    best_url = ""
    best_w = -1

    for part in bgset.split(","):
        part = part.strip()
        if not part:
            continue

        tokens = part.split()
        if len(tokens) < 2:
            continue

        img_url = tokens[0]
        width_token = tokens[1].lower()
        m = re.match(r"(\d+)w", width_token)
        if m:
            w = int(m.group(1))
            if w > best_w:
                best_w = w
                best_url = img_url

    return normalize_url(best_url)


def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def click_load_more_until_target(driver):
    driver.get(URL)
    wait = WebDriverWait(driver, 12)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/products/"]')))

    last_count = 0
    stable_rounds = 0

    while True:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        product_links = soup.select('a[href*="/products/"]')
        current_count = len({a.get("href") for a in product_links if a.get("href")})

        print(f"Current products visible: {current_count}")

        if current_count >= TARGET_PRODUCTS:
            break

        load_more_clicked = False
        buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Load more') or contains(., 'Load More')]")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.6)
                driver.execute_script("arguments[0].click();", btn)
                load_more_clicked = True
                break

        if not load_more_clicked:
            links = driver.find_elements(By.XPATH, "//a[contains(., 'Load more') or contains(., 'Load More')]")
            for lk in links:
                if lk.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", lk)
                    time.sleep(0.6)
                    driver.execute_script("arguments[0].click();", lk)
                    load_more_clicked = True
                    break

        if not load_more_clicked:
            print("No Load more control found anymore.")
            break

        time.sleep(2.0)

        new_html = driver.page_source
        new_soup = BeautifulSoup(new_html, "html.parser")
        new_count = len({
            a.get("href") for a in new_soup.select('a[href*="/products/"]') if a.get("href")
        })

        if new_count <= last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        last_count = new_count
        if stable_rounds >= 2:
            print("Product count not increasing after multiple clicks.")
            break


def extract_one_image_per_product(page_html: str):
    soup = BeautifulSoup(page_html, "html.parser")
    product_to_image = {}

    for a in soup.select('a[href*="/products/"]'):
        href = a.get("href", "").strip()
        if not href:
            continue
        product_url = urljoin(URL, href)

        if product_url in product_to_image:
            continue

        img_url = ""

        bg_div = a.find("div", attrs={"data-bgset": True})
        if bg_div:
            img_url = pick_best_from_bgset(bg_div.get("data-bgset", ""))

        if not img_url:
            src_node = a.select_one("source[srcset], source[data-srcset]")
            if src_node:
                srcset = src_node.get("srcset") or src_node.get("data-srcset")
                img_url = pick_best_from_bgset(srcset)

        if not img_url:
            img_tag = a.find("img")
            if img_tag and img_tag.get("src"):
                img_url = normalize_url(img_tag["src"])

        if img_url:
            product_to_image[product_url] = urljoin(URL, img_url)

        if len(product_to_image) >= TARGET_PRODUCTS:
            break

    return product_to_image


def save_as_jpeg(image_url: str, output_path: str):
    r = requests.get(image_url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(output_path, format="JPEG", quality=92, optimize=True)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    driver = get_driver()

    try:
        click_load_more_until_target(driver)
        html = driver.page_source
    finally:
        driver.quit()

    product_images = extract_one_image_per_product(html)
    items = list(product_images.items())[:TARGET_PRODUCTS]

    print(f"Collected {len(items)} product images.")

    success = 0
    for i, (_, image_url) in enumerate(items, start=1):
        filename = f"{SITE_NAME}_{i}.jpg"
        path = os.path.join(OUT_DIR, filename)
        try:
            save_as_jpeg(image_url, path)
            success += 1
            print(f"[OK] {filename} <- {image_url}")
        except Exception as e:
            print(f"[ERR] {filename} -> {e}")

    print(f"\nDone: saved {success}/{len(items)} JPEG images in '{OUT_DIR}'")


if __name__ == "__main__":
    main()
