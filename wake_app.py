import re
import sys
from playwright.sync_api import sync_playwright

URL = "https://dhfeed-culture.streamlit.app/"
WAKE_TEXT = re.compile("get this app back up", re.I)


def find_wake_button(page):
    # 잠든 화면의 깨우기 버튼을 찾는다 (없으면 None)
    for frame in page.frames:
        button = frame.get_by_role("button", name=WAKE_TEXT)
        if button.count() > 0:
            return button.first
    return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)  # 화면이 뜰 때까지 10초 대기

        button = find_wake_button(page)
        if button:
            print("앱이 잠들어 있음 → 깨우기 버튼 클릭")
            button.click()
            page.wait_for_timeout(60000)  # 앱이 켜질 때까지 60초 대기
            if find_wake_button(page):
                print("실패: 깨우기 버튼이 여전히 보입니다")
                sys.exit(1)
            print("깨우기 완료")
        else:
            print("앱이 이미 깨어 있음 → 20초간 접속 유지")
            page.wait_for_timeout(20000)

        browser.close()


if __name__ == "__main__":
    main()
