# -*- coding: utf-8 -*-
# bot.py — Kengaytirilgan Telegram do'kon-bot (aiogram 3.x, polling)
#
# YANGI FUNKSIYALAR (v2):
#  XARIDOR: Саватча, Qidiruv, Baholash (⭐️), Buyurtmalar tarixi,
#           Referal tizimi, Mahsulot rasm-karuseli, /order_<id> kuzatuv,
#           Matnli izoh (отзыв), FAQ bo'limi
#  ADMIN:   Mahsulot o'chirish/tahrirlash, Buyurtma holati, Statistika,
#           Mahsulot soni (остаток), Ommaviy xabar, Chegirma kodi,
#           Eksport CSV, Kunlik/haftalik avtomatik hisobot (20:00),
#           Xaridorlar ro'yxati (top mijozlar), Izohlarni moderatsiya qilish
#  AVTOMATLASHTIRISH: Саватча eslatmasi (24 soat), "Tez tugaydi" alert,
#           Yangi mahsulot bildirishnomasi obunachilarga

import os
import csv
import io
import json
import math
import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery,
    FSInputFile, BufferedInputFile,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================================================================
# 1) SOZLAMALAR
# ===========================================================================
# ⚠️ MUHIM: Tokenni shu yerga to'g'ridan-to'g'ri yozing (ikkinchi qatordagi
# qo'shtirnoq ichiga). Agar muhit o'zgaruvchisi (export BOT_TOKEN=...) orqali
# bermoqchi bo'lsangiz ham, baribir shu yerga yozib qo'yish ENG ISHONCHLI yo'l —
# ayniqsa Pydroid/QPython kabi mobil dasturlarda muhit o'zgaruvchilari ishlamaydi.
BOT_TOKEN     = os.environ.get("BOT_TOKEN", "8990068735:AAFd9LLwggr0eFmxraDkRPQyLUUHUMleh2Q")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "7391248864")  # masalan: "123456789" yoki "123456789,987654321"
ADMIN_USERNAME = "Behruzik_011"
ADMIN_CONTACT_LINK = f"tg://resolve?domain={ADMIN_USERNAME}"

# ---------------------------------------------------------------------------
# ✅ DASTLABKI TEKSHIRUV — sozlamalar noto'g'ri bo'lsa, dastur shu yerda
# to'xtaydi va ANIQ sababni yozib beradi (jim "Program finished" bo'lmaydi).
# ---------------------------------------------------------------------------
def _sanity_check_settings():
    """Sozlamalarni tekshiradi. Xato topilsa, sababni chop etib False qaytaradi
    (SystemExit chiqarmaydi — chunki bu funksiya import vaqtida chaqirilsa,
    xato konsolda ko'rinmasdan darhol yopilib qolishi mumkin)."""
    errors = []

    token = BOT_TOKEN.strip()
    if not token or token == "BU_YERGA_TOKENINGIZNI_YOZING":
        errors.append(
            "BOT_TOKEN to'ldirilmagan!\n"
            "   → Fayl boshida 'BOT_TOKEN = os.environ.get(...)' qatorida ikkinchi\n"
            "     qo'shtirnoq ichiga @BotFather bergan tokenni yozing.\n"
            "     Masalan: BOT_TOKEN = os.environ.get(\"BOT_TOKEN\", \"123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\")"
        )
    elif ":" not in token:
        errors.append(
            f"BOT_TOKEN formati noto'g'ri ko'rinadi: '{token[:15]}...'\n"
            "   → To'g'ri token har doim RAQAMLAR:HARF-RAQAMLAR ko'rinishida bo'ladi\n"
            "     (masalan: 123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx).\n"
            "   → Tokenni @BotFather'dan qaytadan nusxalab ko'ring, bo'sh joy yoki\n"
            "     qo'shtirnoq tushib qolmaganiga ishonch hosil qiling."
        )
    else:
        parts = token.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or len(parts[1]) < 20:
            errors.append(
                f"BOT_TOKEN formati shubhali: '{token[:15]}...'\n"
                "   → Tokenni @BotFather xabaridan to'liq, boshi-oxiri bilan nusxalang."
            )

    if not ADMIN_CHAT_ID.strip():
        logger.warning(
            "⚠️  ADMIN_CHAT_ID bo'sh qoldirilgan. Bot ishlaydi, lekin yangi buyurtma/\n"
            "    izoh haqida adminga xabar yuborilmaydi. O'z Telegram ID raqamingizni\n"
            "    bilish uchun @userinfobot ga yozing va shu ID'ni ADMIN_CHAT_ID ga qo'ying."
        )

    if errors:
        print("\n" + "="*70)
        print("❌ SOZLAMADA XATO TOPILDI — BOT ISHGA TUSHMAYDI:")
        print("="*70)
        for i, err in enumerate(errors, 1):
            print(f"\n{i}) {err}")
        print("\n" + "="*70)
        print("Xatoni tuzatib, faylni qayta saqlang va yana ishga tushiring.")
        print("="*70 + "\n")
        return False
    return True

_SETTINGS_OK = _sanity_check_settings()

# Bir nechta admin/operatorga xabar yuborish kerak bo'lsa, vergul bilan ajratib yozing:
# ADMIN_CHAT_ID="111111,222222"
def _parse_admin_ids(raw: str):
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(part)
    return ids

ADMIN_IDS = _parse_admin_ids(ADMIN_CHAT_ID)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
ORDERS_FILE   = os.path.join(BASE_DIR, "orders.json")
USERS_FILE    = os.path.join(BASE_DIR, "users.json")
REVIEWS_FILE  = os.path.join(BASE_DIR, "reviews.json")
PROMOS_FILE   = os.path.join(BASE_DIR, "promos.json")
COMMENTS_FILE = os.path.join(BASE_DIR, "comments.json")   # matnli izohlar
FAQ_FILE      = os.path.join(BASE_DIR, "faq.json")

# Саватча eslatmasi qancha vaqtdan keyin yuborilsin (soat)
CART_REMINDER_HOURS = 24
# "Tez tugaydi" ogohlantirish chegarasi (necha dona qolganda)
LOW_STOCK_THRESHOLD = 3
# Kunlik avtomatik hisobot soati (24-soatlik format, server vaqti bo'yicha)
DAILY_REPORT_HOUR = 20
DAILY_REPORT_MINUTE = 0
# Referal uchun чегирма foizi (taklif qiluvchi ham, yangi kelgan ham olishi mumkin)
REFERRAL_DISCOUNT_PERCENT = 10
REFERRAL_BONUS_AFTER_ORDERS = 1   # nechta buyurtmadan keyin taklif qiluvchiga bonus berilsin

# Sodiqlik чегирмаsi: har N zakaz = keyingi zakazda чегирма
LOYALTY_ORDERS_COUNT    = 10   # nechta zakaz = чегирма (masalan: 10)
LOYALTY_DISCOUNT_PERCENT = 10  # чегирма foizi (%)

# ===========================================================================
# YETKAZIB BERISH NARXI SOZLAMALARI
# ===========================================================================
# Boshlang'ich (minimal) narx — har qanday yetkazib berishda olinadigan narx
DELIVERY_BASE_PRICE = 5    # somoni (yoki so'm, o'z valyutangizga o'zgartiring)

# Har 1 km uchun qo'shiladigan narx
DELIVERY_PRICE_PER_KM = 3  # somoni

# Yetkazib berish valyutasi belgisi (ko'rsatish uchun)
DELIVERY_CURRENCY = "сомонӣ"

# Admin lokatsiyasi saqlanadigan fayl (bot avtomatik yangilaydi)
ADMIN_LOCATION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_location.json")

# Admin standart koordinatasi (agar fayl yo'q bo'lsa, shu ishlatiladi)
DEFAULT_ADMIN_LATITUDE  = 39.961563
DEFAULT_ADMIN_LONGITUDE = 69.481998

# Pending delivery calculations: {order_id: {user_id, user_lat, user_lon, cart, lang}}
_pending_delivery: dict = {}
# ===========================================================================

bot     = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp      = Dispatcher(storage=storage)
# ===========================================================================
# 2) TARJIMALAR (21 TIL) — asl nusxa + yangi kalitlar
# ===========================================================================
LANG_BUTTONS = {
    "🇬🇧 English":"en","🇷🇺 Русский":"ru","🇺🇦 Українська":"uk",
    "🇪🇸 Español":"es","🇺🇿 O'zbek":"uz","🇧🇷🇵🇹 Português":"pt",
    "🇩🇪 Deutsch":"de","🇮🇹 Italiano":"it","🇫🇷 Français":"fr",
    "🇹🇷 Türkçe":"tr","🇮🇱 עברית":"he","🇸🇦 العربية":"ar",
    "🇮🇷 زبان فارسی":"fa","🇨🇳 中國人":"zh","🇮🇩 Bahasa Indonesia":"id",
    "🇸🇪 Svenska":"sv","🇲🇾 Melayu":"ms","🇳🇱 Nederlands":"nl",
    "🇮🇳 हिंदी":"hi","🇰🇷 한국인":"ko","🇻🇳 Tiếng Việt":"vi",
}

# Faqat yangi kalitlar uchun tarjimalar (til bo'yicha)
NEW_KEYS = {
    "uz": {
        "cart":"🛒 Саватча","cart_empty":"Сaвaтчaдa ҳеч нарса йўқ.",
        "cart_item":"{name} — {price}","cart_total":"Жами: {count} та маҳсулот",
        "cart_order":"✅ Буюртма бериш","cart_clear":"🗑 Савaтчани тозалаш",
        "added_to_cart":"✅ Сaвaтчaгa қўшилди: {name}",
        "removed_from_cart":"🗑 Ўчирилди: {name}",
        "search":"🔍 Қидириш","search_prompt":"Маҳсулот номини киритинг:",
        "search_no_result":"Ҳеч нарса топилмади.",
        "my_orders":"📦 Буюртмаларим","no_orders":"Ҳали буюртма йўқ.",
        "order_item":"#{id} | {name} | {price} | {status} | {date}",
        "rate_prompt":"Маҳсулотни баҳоланг (1–5 ⭐️):",
        "rate_thanks":"Раҳмат! Сизнинг баҳойингиз: {stars}",
        "rate_btn":"⭐️ Баҳолаш",
        "promo_prompt":"Чегирма кодини киритинг:","promo_invalid":"Нотўғри код.",
        "promo_used":"✅ Код қабул қилинди! Чегирма: {discount}%",
        "promo_btn":"🎟 Промо-код",
        "order_status_new":"🆕 Янги","order_status_accepted":"✅ Қабул қилинди",
        "order_status_delivered":"🚚 Етказилди","order_status_cancelled":"❌ Бекор қилинди",
        "broadcast_sent":"📢 Хабар {count} та фойдаланувчига юборилди.",
        "qty_left":"Қолди: {qty} та",
        "out_of_stock":"❌ Тугаган",
        # --- Referal ---
        "referral_btn":"🤝 Дўстни таклиф қил",
        "referral_info":(
            "🤝 Do'stingizni taklif qiling va чегирма yutib oling!\n\n"
            "Қуйидаги ҳаволани дўстларингизга юборинг. Улар шу ҳавола орқали ботга кирса, "
            "sizga va do'stingizga {discount}% чегирма beriladi.\n\n"
            "🔗 Havolangiz:\n{link}\n\n"
            "👥 Сиз таклиф қилган: {count} киши"
        ),
        "referral_welcome":"🎉 Сиз дўстингизнинг таклифи орқали келдингиз! Биринчи буюртмангизга {discount}% чегирма тайёр.",
        "referral_reward":"🎁 Табрикlaymiz! Дўстингиз биринчи буюртмасини берди — сизга {discount}% чегирма коди тайёрланди: {code}",
        # --- Rasm-karusel ---
        "photo_more":"📸 {current}/{total}-расм",
        # --- Buyurtma kuzatish ---
        "order_track_not_found":"Бундай рақамли буюртма топилмади.\nМисол: /order_5",
        "order_track_usage":"Буюртма рақамини шу кўринишда ёзинг: /order_5",
        # --- Izoh (отзыв) ---
        "comment_btn":"✍️ Изоҳ қолдириш","comment_prompt":"Маҳсулот ҳақида изоҳингизни ёзинг:",
        "comment_thanks":"✅ Раҳмат! Изоҳингиз модерациядан сўнг кўринади.",
        "comment_approved_notice":"✅ Сизнинг изоҳингиз тасдиқланди ва бошқа харидорларга кўринади.",
        "comment_rejected_notice":"❌ Сизнинг изоҳингиз рад этилди.",
        "comments_label":"💬 Мижозлар изоҳлари:",
        "no_comments":"Ҳали изоҳлар йўқ.",
        # --- FAQ ---
        "faq_btn":"❓ Кўп сўраладиган саволлар","faq_empty":"Ҳозирча саволлар қўшилмаган.",
        "faq_title":"❓ Кўп сўраладиган саволлар",
        # --- Eslatmalar / avtomatlashtirish ---
        "cart_reminder":"👋 Salom! Саватчаngizda mahsulotlar kutib turibdi:\n\n{items}\n\nBuyurtmani yakunlashni unutmang!",
        "low_stock_user_warning":"⚠️ Диqqат: \"{name}\" маҳсулотидан фақат {qty} дона қолди!",
        "new_product_notice":"🆕 Yangi mahsulot qo'shildi!\n\n<b>{name}</b>\n{price}\n\n{description}",
        # --- Yetkazib berish narxi ---
        "delivery_location_request":"📍 Етказиб бериш нархини билиш учун жойлашувингизни юборинг:",
        "delivery_location_btn":"📍 Жойлашувимни юбориш",
        "delivery_price_result":(
            "🚚 Yetkazib berish narxi:\n\n"
            "📏 Masofa: ~{km:.1f} km\n"
            "💰 Boshlang'ich narx: {base} {currency}\n"
            "➕ Masofa narxi: {km_price:.0f} {currency}\n"
            "━━━━━━━━━━━━━━━\n"
            "💵 Yetkazib berish: <b>{delivery} {currency}</b>\n"
            "🛒 Mahsulotlar: {products_total}\n"
            "━━━━━━━━━━━━━━━\n"
            "✅ Жами: <b>{grand_total}</b>"
        ),
        "delivery_added_to_order":"✅ Етказиб бериш нархи ({delivery} {currency}) буюртмага қўшилди.",
        "delivery_skip":"⏭ Етказиб беришсиз давом этиш",
    },
    "ru": {
        "cart":"🛒 Корзина","cart_empty":"Корзина пуста.",
        "cart_item":"{name} — {price}","cart_total":"Итого: {count} товар(а)",
        "cart_order":"✅ Оформить заказ","cart_clear":"🗑 Очистить корзину",
        "added_to_cart":"✅ Добавлено в корзину: {name}",
        "removed_from_cart":"🗑 Удалено: {name}",
        "search":"🔍 Поиск","search_prompt":"Введите название товара:",
        "search_no_result":"Ничего не найдено.",
        "my_orders":"📦 Мои заказы","no_orders":"Заказов пока нет.",
        "order_item":"#{id} | {name} | {price} | {status} | {date}",
        "rate_prompt":"Оцените товар (1–5 ⭐️):","rate_thanks":"Спасибо! Ваша оценка: {stars}",
        "rate_btn":"⭐️ Оценить",
        "promo_prompt":"Введите промокод:","promo_invalid":"Неверный код.",
        "promo_used":"✅ Код принят! Скидка: {discount}%","promo_btn":"🎟 Промокод",
        "order_status_new":"🆕 Новый","order_status_accepted":"✅ Принят",
        "order_status_delivered":"🚚 Доставлен","order_status_cancelled":"❌ Отменён",
        "broadcast_sent":"📢 Сообщение отправлено {count} пользователям.",
        "qty_left":"Осталось: {qty} шт.","out_of_stock":"❌ Нет в наличии",
        "referral_btn":"🤝 Пригласить друга",
        "referral_info":(
            "🤝 Пригласите друга и получите скидку!\n\n"
            "Отправьте эту ссылку друзьям. Когда они зайдут в бота по ней, "
            "вы и ваш друг получите скидку {discount}%.\n\n"
            "🔗 Ваша ссылка:\n{link}\n\n"
            "👥 Вы пригласили: {count} человек"
        ),
        "referral_welcome":"🎉 Вы пришли по приглашению друга! На первый заказ скидка {discount}%.",
        "referral_reward":"🎁 Поздравляем! Ваш друг сделал первый заказ — для вас готов промокод на скидку {discount}%: {code}",
        "photo_more":"📸 Фото {current}/{total}",
        "order_track_not_found":"Заказ с таким номером не найден или он не принадлежит вам.\nПример: /order_5",
        "order_track_usage":"Введите номер заказа в формате: /order_5",
        "comment_btn":"✍️ Оставить отзыв","comment_prompt":"Напишите отзыв о товаре:",
        "comment_thanks":"✅ Спасибо! Ваш отзыв появится после проверки модератором.",
        "comment_approved_notice":"✅ Ваш отзыв одобрен и виден другим покупателям.",
        "comment_rejected_notice":"❌ Ваш отзыв был отклонён.",
        "comments_label":"💬 Отзывы покупателей:",
        "no_comments":"Отзывов пока нет.",
        "faq_btn":"❓ Часто задаваемые вопросы","faq_empty":"Вопросы пока не добавлены.",
        "faq_title":"❓ Часто задаваемые вопросы",
        "cart_reminder":"👋 Привет! В вашей корзине ждут товары:\n\n{items}\n\nНе забудьте оформить заказ!",
        "low_stock_user_warning":"⚠️ Внимание: товара \"{name}\" осталось всего {qty} шт.!",
        "new_product_notice":"🆕 Новый товар!\n\n<b>{name}</b>\n{price}\n\n{description}",
        # --- Yetkazib berish narxi ---
        "delivery_location_request":"📍 Чтобы рассчитать стоимость доставки, отправьте ваше местоположение:",
        "delivery_location_btn":"📍 Отправить местоположение",
        "delivery_price_result":(
            "🚚 Стоимость доставки:\n\n"
            "📏 Расстояние: ~{km:.1f} км\n"
            "💰 Базовая цена: {base} {currency}\n"
            "➕ За расстояние: {km_price:.0f} {currency}\n"
            "━━━━━━━━━━━━━━━\n"
            "💵 Доставка: <b>{delivery} {currency}</b>\n"
            "🛒 Товары: {products_total}\n"
            "━━━━━━━━━━━━━━━\n"
            "✅ Итого: <b>{grand_total}</b>"
        ),
        "delivery_added_to_order":"✅ Стоимость доставки ({delivery} {currency}) добавлена к заказу.",
        "delivery_skip":"⏭ Продолжить без доставки",
    },
    "en": {
        "cart":"🛒 Cart","cart_empty":"Your cart is empty.",
        "cart_item":"{name} — {price}","cart_total":"Total: {count} item(s)",
        "cart_order":"✅ Place order","cart_clear":"🗑 Clear cart",
        "added_to_cart":"✅ Added to cart: {name}",
        "removed_from_cart":"🗑 Removed: {name}",
        "search":"🔍 Search","search_prompt":"Enter product name:",
        "search_no_result":"Nothing found.",
        "my_orders":"📦 My orders","no_orders":"No orders yet.",
        "order_item":"#{id} | {name} | {price} | {status} | {date}",
        "rate_prompt":"Rate this product (1–5 ⭐️):","rate_thanks":"Thanks! Your rating: {stars}",
        "rate_btn":"⭐️ Rate",
        "promo_prompt":"Enter promo code:","promo_invalid":"Invalid code.",
        "promo_used":"✅ Code accepted! Discount: {discount}%","promo_btn":"🎟 Promo code",
        "order_status_new":"🆕 New","order_status_accepted":"✅ Accepted",
        "order_status_delivered":"🚚 Delivered","order_status_cancelled":"❌ Cancelled",
        "broadcast_sent":"📢 Message sent to {count} users.",
        "qty_left":"In stock: {qty}","out_of_stock":"❌ Out of stock",
        "referral_btn":"🤝 Invite a friend",
        "referral_info":(
            "🤝 Invite a friend and get a discount!\n\n"
            "Send this link to your friends. When they join the bot through it, "
            "you and your friend both get {discount}% off.\n\n"
            "🔗 Your link:\n{link}\n\n"
            "👥 People you invited: {count}"
        ),
        "referral_welcome":"🎉 You joined via a friend's invite! Your first order gets {discount}% off.",
        "referral_reward":"🎁 Congrats! Your friend placed their first order — here's your {discount}% discount code: {code}",
        "photo_more":"📸 Photo {current}/{total}",
        "order_track_not_found":"No order with that number found, or it isn't yours.\nExample: /order_5",
        "order_track_usage":"Type the order number like this: /order_5",
        "comment_btn":"✍️ Leave a review","comment_prompt":"Write your review about this product:",
        "comment_thanks":"✅ Thanks! Your review will appear after moderation.",
        "comment_approved_notice":"✅ Your review has been approved and is visible to other buyers.",
        "comment_rejected_notice":"❌ Your review was rejected.",
        "comments_label":"💬 Customer reviews:",
        "no_comments":"No reviews yet.",
        "faq_btn":"❓ FAQ","faq_empty":"No questions added yet.",
        "faq_title":"❓ Frequently Asked Questions",
        "cart_reminder":"👋 Hi! Items are waiting in your cart:\n\n{items}\n\nDon't forget to complete your order!",
        "low_stock_user_warning":"⚠️ Note: only {qty} left of \"{name}\"!",
        "new_product_notice":"🆕 New product!\n\n<b>{name}</b>\n{price}\n\n{description}",
        # --- Delivery price ---
        "delivery_location_request":"📍 Send your location to calculate the delivery price:",
        "delivery_location_btn":"📍 Share my location",
        "delivery_price_result":(
            "🚚 Delivery cost:\n\n"
            "📏 Distance: ~{km:.1f} km\n"
            "💰 Base price: {base} {currency}\n"
            "➕ Distance fee: {km_price:.0f} {currency}\n"
            "━━━━━━━━━━━━━━━\n"
            "💵 Delivery: <b>{delivery} {currency}</b>\n"
            "🛒 Products: {products_total}\n"
            "━━━━━━━━━━━━━━━\n"
            "✅ Grand total: <b>{grand_total}</b>"
        ),
        "delivery_added_to_order":"✅ Delivery fee ({delivery} {currency}) added to your order.",
        "delivery_skip":"⏭ Continue without delivery",
    },
}
# Boshqa tillar uchun inglizcha fallback
for _l in LANG_BUTTONS.values():
    if _l not in NEW_KEYS:
        NEW_KEYS[_l] = NEW_KEYS["en"]
TEXTS = {'uz': {'choose_lang': 'Тилни танланг:','lang_set': 'Тил танланди: Ўзбекча ✅',
        'main_menu': 'Асосий менью. Бўлимни танланг:','back': '⬅️ Орқага','to_main': '🏠 Бош менью',
        'choose_product': 'Маҳсулотни танланг:','price': 'Нарх','description': 'Тавсиф',
        'buy_btn': '🛒 Сотиб олиш','contact_btn': '📞 Боғланиш',
        'order_sent': '✅ Сўровингиз қабул қилинди!\n\nМаҳсулот: {name}\nНарх: {price}\n\nқуйидаги тугма орқали биз билан тўғридан-тўғри боғланишингиз мумкин.',
        'contact_link_text': '👉 Алоқа учун босинг','not_found': 'Илтимос, меньюдаги тугмалардан бирини танланг.',
        'delivery_name': '🚚 Етказиб бериш хизмати',
        'delivery_info': 'Биз маҳсулотни манзилингизга етказиб берамиз.\n\nБуюртма бериш учун пастдаги тугмани босинг, операторимиз сиз билан боғланади.',
        'categories_label': 'БЎЛИМЛАР',
        'categories': {'electronics':'📱 Электроника','auto':'🚗 Машина','home':'🏠 Уй-хўжалик',
                       'fruits':'🍎 Мевалар','vegetables':'🥦 Сабзавотлар','kids':'👶 Болалар учун','clothes':'🛍️ Кийим-кечаклар','spare_parts':'🔧 Запчастлар','food':'🍽️ Озиқ-овқат','pharmacy':'💊 Доrixona/гигиена','delivery':'🚚 Етказиб бериш'},
        'empty_category': '📭 Ҳозирча бу бўлимда маҳсулот йўқ.'},
 'ru': {'choose_lang': 'Выберите язык:','lang_set': 'Язык выбран: Русский ✅',
        'main_menu': 'Главное меню. Выберите раздел:','back': '⬅️ Назад','to_main': '🏠 Главное меню',
        'choose_product': 'Выберите товар:','price': 'Цена','description': 'Описание',
        'buy_btn': '🛒 Купить','contact_btn': '📞 Связаться',
        'order_sent': '✅ Ваш запрос принят!\n\nТовар: {name}\nЦена: {price}\n\nВы можете связаться с нами напрямую через кнопку ниже.',
        'contact_link_text': '👉 Нажмите для связи','not_found': 'Пожалуйста, выберите кнопку из меню.',
        'delivery_name': '🚚 Служба доставки',
        'delivery_info': 'Мы доставим товар по вашему адресу.\n\nЧтобы оформить заказ, нажмите кнопку ниже — наш оператор свяжется с вами.',
        'categories_label': 'РАЗДЕЛЫ',
        'categories': {'electronics':'📱 Электроника','auto':'🚗 Авто','home':'🏠 Хозтовары',
                       'fruits':'🍎 Фрукты','vegetables':'🥦 Овощи','kids':'👶 Для детей','clothes':'🛍️ Одежда','spare_parts':'🔧 Запчасти','food':'🍽️ Продукты','pharmacy':'💊 Аптека/гигиена','delivery':'🚚 Доставка'},
        'empty_category': '📭 В этом разделе пока нет товаров.'},
 'en': {'choose_lang': 'Choose your language:','lang_set': 'Language set: English ✅',
        'main_menu': 'Main menu. Choose a section:','back': '⬅️ Back','to_main': '🏠 Main menu',
        'choose_product': 'Choose a product:','price': 'Price','description': 'Description',
        'buy_btn': '🛒 Buy','contact_btn': '📞 Contact us',
        'order_sent': '✅ Your request has been received!\n\nProduct: {name}\nPrice: {price}\n\nYou can contact us directly using the button below.',
        'contact_link_text': '👉 Tap to contact','not_found': 'Please choose a button from the menu.',
        'delivery_name': '🚚 Delivery service',
        'delivery_info': 'We deliver the product to your address.\n\nTo place an order, tap the button below — our operator will contact you.',
        'categories_label': 'SECTIONS',
        'categories': {'electronics':'📱 Electronics','auto':'🚗 Auto','home':'🏠 Household',
                       'fruits':'🍎 Fruits','vegetables':'🥦 Vegetables','kids':'👶 For kids','clothes':'🛍️ Clothing','spare_parts':'🔧 Spare parts','food':'🍽️ Food','pharmacy':'💊 Pharmacy/hygiene','delivery':'🚚 Delivery'},
        'empty_category': '📭 No products in this section yet.'},
 'uk': {'choose_lang': 'Виберіть мову:','lang_set': 'Мову обрано: Українська ✅',
        'main_menu': 'Головне меню. Виберіть розділ:','back': '⬅️ Назад','to_main': '🏠 Головне меню',
        'choose_product': 'Виберіть товар:','price': 'Ціна','description': 'Опис',
        'buy_btn': '🛒 Купити','contact_btn': "📞 Зв'язатися",
        'order_sent': "✅ Ваш запит прийнято!\n\nТовар: {name}\nЦіна: {price}\n\nВи можете зв'язатися з нами напряму через кнопку нижче.",
        'contact_link_text': "👉 Натисніть для зв'язку",'not_found': 'Будь ласка, виберіть кнопку з меню.',
        'delivery_name': '🚚 Служба доставки',
        'delivery_info': "Ми доставимо товар за вашою адресою.\n\nЩоб оформити замовлення, натисніть кнопку нижче — наш оператор зв'яжеться з вами.",
        'categories_label': 'РОЗДІЛИ',
        'categories': {'electronics':'📱 Електроніка','auto':'🚗 Авто','home':'🏠 Товари для дому',
                       'fruits':'🍎 Фрукти','vegetables':'🥦 Овочі','kids':'👶 Для дітей','clothes':'👗 Одяг','delivery':'🚚 Доставка'},
        'empty_category': '📭 У цьому розділі поки немає товарів.'},
 'es': {'choose_lang': 'Elige tu idioma:','lang_set': 'Idioma seleccionado: Español ✅',
        'main_menu': 'Menú principal. Elige una sección:','back': '⬅️ Atrás','to_main': '🏠 Menú principal',
        'choose_product': 'Elige un producto:','price': 'Precio','description': 'Descripción',
        'buy_btn': '🛒 Comprar','contact_btn': '📞 Contactar',
        'order_sent': '✅ ¡Su solicitud ha sido recibida!\n\nProducto: {name}\nPrecio: {price}\n\nPuede contactarnos directamente usando el botón de abajo.',
        'contact_link_text': '👉 Toque para contactar','not_found': 'Por favor, elija un botón del menú.',
        'delivery_name': '🚚 Servicio de entrega',
        'delivery_info': 'Entregamos el producto en su dirección.\n\nPara hacer un pedido, toque el botón de abajo — nuestro operador se pondrá en contacto con usted.',
        'categories_label': 'SECCIONES',
        'categories': {'electronics':'📱 Electrónica','auto':'🚗 Auto','home':'🏠 Hogar',
                       'fruits':'🍎 Frutas','vegetables':'🥦 Verduras','kids':'👶 Para niños','clothes':'👗 Ropa','delivery':'🚚 Entrega'},
        'empty_category': '📭 Todavía no hay productos en esta sección.'},
 'pt': {'choose_lang': 'Escolha seu idioma:','lang_set': 'Idioma selecionado: Português ✅',
        'main_menu': 'Menu principal. Escolha uma seção:','back': '⬅️ Voltar','to_main': '🏠 Menu principal',
        'choose_product': 'Escolha um produto:','price': 'Preço','description': 'Descrição',
        'buy_btn': '🛒 Comprar','contact_btn': '📞 Contato',
        'order_sent': '✅ Seu pedido foi recebido!\n\nProduto: {name}\nPreço: {price}\n\nVocê pode entrar em contato conosco diretamente usando o botão abaixo.',
        'contact_link_text': '👉 Toque para contato','not_found': 'Por favor, escolha um botão do menu.',
        'delivery_name': '🚚 Serviço de entrega',
        'delivery_info': 'Entregamos o produto no seu endereço.\n\nPara fazer um pedido, toque no botão abaixo — nosso operador entrará em contato.',
        'categories_label': 'SEÇÕES',
        'categories': {'electronics':'📱 Eletrônicos','auto':'🚗 Carros','home':'🏠 Casa',
                       'fruits':'🍎 Frutas','vegetables':'🥦 Vegetais','delivery':'🚚 Entrega'},
        'empty_category': '📭 Ainda não há produtos nesta seção.'},
 'de': {'choose_lang': 'Wählen Sie Ihre Sprache:','lang_set': 'Sprache gewählt: Deutsch ✅',
        'main_menu': 'Hauptmenü. Wählen Sie einen Bereich:','back': '⬅️ Zurück','to_main': '🏠 Hauptmenü',
        'choose_product': 'Wählen Sie ein Produkt:','price': 'Preis','description': 'Beschreibung',
        'buy_btn': '🛒 Kaufen','contact_btn': '📞 Kontakt',
        'order_sent': '✅ Ihre Anfrage wurde empfangen!\n\nProdukt: {name}\nPreis: {price}\n\nSie können uns direkt über die Schaltfläche unten kontaktieren.',
        'contact_link_text': '👉 Tippen Sie für Kontakt','not_found': 'Bitte wählen Sie eine Schaltfläche aus dem Menü.',
        'delivery_name': '🚚 Lieferservice',
        'delivery_info': 'Wir liefern das Produkt an Ihre Adresse.\n\nUm zu bestellen, tippen Sie auf die Schaltfläche unten — unser Mitarbeiter wird sich mit Ihnen in Verbindung setzen.',
        'categories_label': 'BEREICHE',
        'categories': {'electronics':'📱 Elektronik','auto':'🚗 Auto','home':'🏠 Haushalt',
                       'fruits':'🍎 Obst','vegetables':'🥦 Gemüse','kids':'👶 Für Kinder','clothes':'👗 Kleidung','delivery':'🚚 Lieferung'},
        'empty_category': '📭 In diesem Bereich gibt es noch keine Produkte.'},
 'it': {'choose_lang': 'Scegli la tua lingua:','lang_set': 'Lingua selezionata: Italiano ✅',
        'main_menu': 'Menu principale. Scegli una sezione:','back': '⬅️ Indietro','to_main': '🏠 Menu principale',
        'choose_product': 'Scegli un prodotto:','price': 'Prezzo','description': 'Descrizione',
        'buy_btn': '🛒 Acquista','contact_btn': '📞 Contattaci',
        'order_sent': '✅ La tua richiesta è stata ricevuta!\n\nProdotto: {name}\nPrezzo: {price}\n\nPuoi contattarci direttamente usando il pulsante qui sotto.',
        'contact_link_text': '👉 Tocca per contattare','not_found': 'Si prega di scegliere un pulsante dal menu.',
        'delivery_name': '🚚 Servizio di consegna',
        'delivery_info': 'Consegniamo il prodotto al tuo indirizzo.\n\nPer effettuare un ordine, tocca il pulsante qui sotto — il nostro operatore ti contatterà.',
        'categories_label': 'SEZIONI',
        'categories': {'electronics':'📱 Elettronica','auto':'🚗 Auto','home':'🏠 Casa',
                       'fruits':'🍎 Frutta','vegetables':'🥦 Verdure','delivery':'🚚 Consegna'},
        'empty_category': '📭 Non ci sono ancora prodotti in questa sezione.'},
 'fr': {'choose_lang': 'Choisissez votre langue:','lang_set': 'Langue sélectionnée: Français ✅',
        'main_menu': 'Menu principal. Choisissez une section:','back': '⬅️ Retour','to_main': '🏠 Menu principal',
        'choose_product': 'Choisissez un produit:','price': 'Prix','description': 'Description',
        'buy_btn': '🛒 Acheter','contact_btn': '📞 Contact',
        'order_sent': '✅ Votre demande a été reçue!\n\nProduit: {name}\nPrix: {price}\n\nVous pouvez nous contacter directement via le bouton ci-dessous.',
        'contact_link_text': '👉 Appuyez pour contacter','not_found': 'Veuillez choisir un bouton dans le menu.',
        'delivery_name': '🚚 Service de livraison',
        'delivery_info': 'Nous livrons le produit à votre adresse.\n\nPour passer une commande, appuyez sur le bouton ci-dessous — notre opérateur vous contactera.',
        'categories_label': 'SECTIONS',
        'categories': {'electronics':'📱 Électronique','auto':'🚗 Auto','home':'🏠 Maison',
                       'fruits':'🍎 Fruits','vegetables':'🥦 Légumes','kids':'👶 Pour enfants','clothes':'👗 Vêtements','delivery':'🚚 Livraison'},
        'empty_category': "📭 Il n'y a pas encore de produits dans cette section."},
 'tr': {'choose_lang': 'Dilinizi seçin:','lang_set': 'Dil seçildi: Türkçe ✅',
        'main_menu': 'Ana menü. Bir bölüm seçin:','back': '⬅️ Geri','to_main': '🏠 Ana menü',
        'choose_product': 'Bir ürün seçin:','price': 'Fiyat','description': 'Açıklama',
        'buy_btn': '🛒 Satın al','contact_btn': '📞 İletişim',
        'order_sent': '✅ Talebiniz alındı!\n\nÜrün: {name}\nFiyat: {price}\n\nAşağıdaki düğmeyi kullanarak doğrudan bizimle iletişime geçebilirsiniz.',
        'contact_link_text': '👉 İletişim için dokunun','not_found': 'Lütfen menüden bir düğme seçin.',
        'delivery_name': '🚚 Teslimat hizmeti',
        'delivery_info': 'Ürünü adresinize teslim ediyoruz.\n\nSipariş vermek için aşağıdaki düğmeye dokunun — operatörümüz sizinle iletişime geçecek.',
        'categories_label': 'BÖLÜMLER',
        'categories': {'electronics':'📱 Elektronik','auto':'🚗 Araba','home':'🏠 Ev eşyaları',
                       'fruits':'🍎 Meyveler','vegetables':'🥦 Sebzeler','delivery':'🚚 Teslimat'},
        'empty_category': '📭 Bu bölümde henüz ürün yok.'},
 'he': {'choose_lang': 'בחר את השפה שלך:','lang_set': 'השפה נבחרה: עברית ✅',
        'main_menu': 'תפריט ראשי. בחר קטגוריה:','back': '⬅️ חזרה','to_main': '🏠 תפריט ראשי',
        'choose_product': 'בחר מוצר:','price': 'מחיר','description': 'תיאור',
        'buy_btn': '🛒 קנייה','contact_btn': '📞 צור קשר',
        'order_sent': '✅ הבקשה שלך התקבלה!\n\nמוצר: {name}\nמחיר: {price}\n\nתוכל ליצור איתנו קשר ישירות באמצעות הכפתור למטה.',
        'contact_link_text': '👉 הקש ליצירת קשר','not_found': 'אנא בחר כפתור מהתפריט.',
        'delivery_name': '🚚 שירות משלוחים',
        'delivery_info': 'אנחנו מספקים את המוצר לכתובת שלך.\n\nכדי לבצע הזמנה, הקש על הכפתור למטה — הנציג שלנו ייצור איתך קשר.',
        'categories_label': 'קטגוריות',
        'categories': {'electronics':'📱 אלקטרוניקה','auto':'🚗 רכב','home':'🏠 לבית',
                       'fruits':'🍎 פירות','vegetables':'🥦 ירקות','kids':'👶 לילדים','clothes':'👗 ביגוד','delivery':'🚚 משלוח'},
        'empty_category': '📭 אין עדיין מוצרים בקטגוריה זו.'},
 'ar': {'choose_lang': 'اختر لغتك:','lang_set': 'تم اختيار اللغة: العربية ✅',
        'main_menu': 'القائمة الرئيسية. اختر قسماً:','back': '⬅️ رجوع','to_main': '🏠 القائمة الرئيسية',
        'choose_product': 'اختر منتجاً:','price': 'السعر','description': 'الوصف',
        'buy_btn': '🛒 شراء','contact_btn': '📞 تواصل معنا',
        'order_sent': '✅ تم استلام طلبك!\n\nالمنتج: {name}\nالسعر: {price}\n\nيمكنك التواصل معنا مباشرة عبر الزر أدناه.',
        'contact_link_text': '👉 اضغط للتواصل','not_found': 'الرجاء اختيار زر من القائمة.',
        'delivery_name': '🚚 خدمة التوصيل',
        'delivery_info': 'نقوم بتوصيل المنتج إلى عنوانك.\n\nلتقديم الطلب، اضغط على الزر أدناه — سيتواصل معك موظفنا.',
        'categories_label': 'الأقسام',
        'categories': {'electronics':'📱 إلكترونيات','auto':'🚗 سيارات','home':'🏠 المنزل',
                       'fruits':'🍎 فواكه','vegetables':'🥦 خضروات','delivery':'🚚 التوصيل'},
        'empty_category': '📭 لا توجد منتجات في هذا القسم بعد.'},
 'fa': {'choose_lang': 'زبان خود را انتخاب کنید:','lang_set': 'زبان انتخاب شد: فارسی ✅',
        'main_menu': 'منوی اصلی. یک بخش را انتخاب کنید:','back': '⬅️ بازگشت','to_main': '🏠 منوی اصلی',
        'choose_product': 'یک محصول را انتخاب کنید:','price': 'قیمت','description': 'توضیحات',
        'buy_btn': '🛒 خرید','contact_btn': '📞 تماس با ما',
        'order_sent': '✅ درخواست شما دریافت شد!\n\nمحصول: {name}\nقیمت: {price}\n\nمی\u200cتوانید مستقیماً از طریق دکمه زیر با ما تماس بگیرید.',
        'contact_link_text': '👉 برای تماس ضربه بزنید','not_found': 'لطفاً یک دکمه از منو انتخاب کنید.',
        'delivery_name': '🚚 خدمات تحویل',
        'delivery_info': 'ما محصول را به آدرس شما تحویل می\u200cدهیم.\n\nبرای ثبت سفارش، دکمه زیر را لمس کنید — اپراتور ما با شما تماس خواهد گرفت.',
        'categories_label': 'بخش\u200cها',
        'categories': {'electronics':'📱 لوازم الکترونیکی','auto':'🚗 خودرو','home':'🏠 خانه و آشپزخانه',
                       'fruits':'🍎 میوه\u200cها','vegetables':'🥦 سبزیجات','delivery':'🚚 تحویل'},
        'empty_category': '📭 هنوز محصولی در این بخش وجود ندارد.'},
 'zh': {'choose_lang': '选择您的语言：','lang_set': '语言已选择：中文 ✅',
        'main_menu': '主菜单。请选择一个类别：','back': '⬅️ 返回','to_main': '🏠 主菜单',
        'choose_product': '请选择产品：','price': '价格','description': '描述',
        'buy_btn': '🛒 购买','contact_btn': '📞 联系我们',
        'order_sent': '✅ 您的请求已收到！\n\n产品：{name}\n价格：{price}\n\n您可以通过下面的按钮直接联系我们。',
        'contact_link_text': '👉 点击联系','not_found': '请从菜单中选择一个按钮。',
        'delivery_name': '🚚 送货服务',
        'delivery_info': '我们将产品送到您的地址。\n\n要下订单，请点击下面的按钮——我们的客服将与您联系。',
        'categories_label': '类别',
        'categories': {'electronics':'📱 电子产品','auto':'🚗 汽车','home':'🏠 家居用品',
                       'fruits':'🍎 水果','vegetables':'🥦 蔬菜','kids':'👶 儿童用品','clothes':'👗 服装','delivery':'🚚 配送'},
        'empty_category': '📭 此分类暂无产品。'},
 'id': {'choose_lang': 'Pilih bahasa Anda:','lang_set': 'Bahasa dipilih: Bahasa Indonesia ✅',
        'main_menu': 'Menu utama. Pilih bagian:','back': '⬅️ Kembali','to_main': '🏠 Menu utama',
        'choose_product': 'Pilih produk:','price': 'Harga','description': 'Deskripsi',
        'buy_btn': '🛒 Beli','contact_btn': '📞 Hubungi kami',
        'order_sent': '✅ Permintaan Anda telah diterima!\n\nProduk: {name}\nHarga: {price}\n\nAnda dapat menghubungi kami langsung melalui tombol di bawah.',
        'contact_link_text': '👉 Ketuk untuk menghubungi','not_found': 'Silakan pilih tombol dari menu.',
        'delivery_name': '🚚 Layanan pengiriman',
        'delivery_info': 'Kami mengirimkan produk ke alamat Anda.\n\nUntuk memesan, ketuk tombol di bawah — operator kami akan menghubungi Anda.',
        'categories_label': 'BAGIAN',
        'categories': {'electronics':'📱 Elektronik','auto':'🚗 Mobil','home':'🏠 Rumah Tangga',
                       'fruits':'🍎 Buah-buahan','vegetables':'🥦 Sayuran','delivery':'🚚 Pengiriman'},
        'empty_category': '📭 Belum ada produk di bagian ini.'},
 'sv': {'choose_lang': 'Välj ditt språk:','lang_set': 'Språk valt: Svenska ✅',
        'main_menu': 'Huvudmeny. Välj en kategori:','back': '⬅️ Tillbaka','to_main': '🏠 Huvudmeny',
        'choose_product': 'Välj en produkt:','price': 'Pris','description': 'Beskrivning',
        'buy_btn': '🛒 Köp','contact_btn': '📞 Kontakta oss',
        'order_sent': '✅ Din förfrågan har mottagits!\n\nProdukt: {name}\nPris: {price}\n\nDu kan kontakta oss direkt via knappen nedan.',
        'contact_link_text': '👉 Tryck för att kontakta','not_found': 'Vänligen välj en knapp från menyn.',
        'delivery_name': '🚚 Leveranstjänst',
        'delivery_info': 'Vi levererar produkten till din adress.\n\nFör att beställa, tryck på knappen nedan — vår operatör kontaktar dig.',
        'categories_label': 'KATEGORIER',
        'categories': {'electronics':'📱 Elektronik','auto':'🚗 Bil','home':'🏠 Hushåll',
                       'fruits':'🍎 Frukt','vegetables':'🥦 Grönsaker','kids':'👶 För barn','clothes':'👗 Kläder','delivery':'🚚 Leverans'},
        'empty_category': '📭 Det finns inga produkter i den här kategorin än.'},
 'ms': {'choose_lang': 'Pilih bahasa anda:','lang_set': 'Bahasa dipilih: Melayu ✅',
        'main_menu': 'Menu utama. Pilih bahagian:','back': '⬅️ Kembali','to_main': '🏠 Menu utama',
        'choose_product': 'Pilih produk:','price': 'Harga','description': 'Penerangan',
        'buy_btn': '🛒 Beli','contact_btn': '📞 Hubungi kami',
        'order_sent': '✅ Permintaan anda telah diterima!\n\nProduk: {name}\nHarga: {price}\n\nAnda boleh menghubungi kami terus melalui butang di bawah.',
        'contact_link_text': '👉 Ketik untuk hubungi','not_found': 'Sila pilih butang daripada menu.',
        'delivery_name': '🚚 Perkhidmatan penghantaran',
        'delivery_info': 'Kami menghantar produk ke alamat anda.\n\nUntuk membuat pesanan, ketik butang di bawah — operator kami akan menghubungi anda.',
        'categories_label': 'BAHAGIAN',
        'categories': {'electronics':'📱 Elektronik','auto':'🚗 Kereta','home':'🏠 Rumah Tangga',
                       'fruits':'🍎 Buah-buahan','vegetables':'🥦 Sayur-sayuran','kids':'👶 Untuk kanak-kanak','clothes':'👗 Pakaian','delivery':'🚚 Penghantaran'},
        'empty_category': '📭 Belum ada produk dalam bahagian ini.'},
 'nl': {'choose_lang': 'Kies uw taal:','lang_set': 'Taal gekozen: Nederlands ✅',
        'main_menu': 'Hoofdmenu. Kies een categorie:','back': '⬅️ Terug','to_main': '🏠 Hoofdmenu',
        'choose_product': 'Kies een product:','price': 'Prijs','description': 'Beschrijving',
        'buy_btn': '🛒 Kopen','contact_btn': '📞 Contact',
        'order_sent': '✅ Uw aanvraag is ontvangen!\n\nProduct: {name}\nPrijs: {price}\n\nU kunt rechtstreeks contact met ons opnemen via de knop hieronder.',
        'contact_link_text': '👉 Tik om contact op te nemen','not_found': 'Kies een knop uit het menu.',
        'delivery_name': '🚚 Bezorgservice',
        'delivery_info': 'Wij bezorgen het product op uw adres.\n\nOm te bestellen, tik op de knop hieronder — onze medewerker neemt contact met u op.',
        'categories_label': 'CATEGORIEËN',
        'categories': {'electronics':'📱 Elektronica','auto':'🚗 Auto','home':'🏠 Huishouden',
                       'fruits':'🍎 Fruit','vegetables':'🥦 Groenten','kids':'👶 Voor kinderen','clothes':'👗 Kleding','delivery':'🚚 Bezorging'},
        'empty_category': '📭 Er zijn nog geen producten in deze categorie.'},
 'hi': {'choose_lang': 'अपनी भाषा चुनें:','lang_set': 'भाषा चयनित: हिंदी ✅',
        'main_menu': 'मुख्य मेनू। एक श्रेणी चुनें:','back': '⬅️ वापस','to_main': '🏠 मुख्य मेनू',
        'choose_product': 'एक उत्पाद चुनें:','price': 'कीमत','description': 'विवरण',
        'buy_btn': '🛒 खरीदें','contact_btn': '📞 संपर्क करें',
        'order_sent': '✅ आपका अनुरोध प्राप्त हो गया है!\n\nउत्पाद: {name}\nकीमत: {price}\n\nआप नीचे दिए गए बटन के माध्यम से सीधे हमसे संपर्क कर सकते हैं।',
        'contact_link_text': '👉 संपर्क के लिए टैप करें','not_found': 'कृपया मेनू से एक बटन चुनें।',
        'delivery_name': '🚚 डिलीवरी सेवा',
        'delivery_info': 'हम उत्पाद को आपके पते पर पहुंचाते हैं।\n\nऑर्डर करने के लिए, नीचे दिए गए बटन को टैप करें — हमारा ऑपरेटर आपसे संपर्क करेगा।',
        'categories_label': 'श्रेणियाँ',
        'categories': {'electronics':'📱 इलेक्ट्रॉनिक्स','auto':'🚗 कार','home':'🏠 घरेलू सामान',
                       'fruits':'🍎 फल','vegetables':'🥦 सब्जियां','kids':'👶 बच्चों के लिए','clothes':'👗 कपड़े','delivery':'🚚 डिलीवरी'},
        'empty_category': '📭 इस श्रेणी में अभी तक कोई उत्पाद नहीं है।'},
 'ko': {'choose_lang': '언어를 선택하세요:','lang_set': '언어 선택됨: 한국어 ✅',
        'main_menu': '메인 메뉴. 카테고리를 선택하세요:','back': '⬅️ 뒤로','to_main': '🏠 메인 메뉴',
        'choose_product': '상품을 선택하세요:','price': '가격','description': '설명',
        'buy_btn': '🛒 구매','contact_btn': '📞 문의하기',
        'order_sent': '✅ 요청이 접수되었습니다!\n\n상품: {name}\n가격: {price}\n\n아래 버튼을 통해 직접 문의하실 수 있습니다.',
        'contact_link_text': '👉 문의하려면 탭하세요','not_found': '메뉴에서 버튼을 선택해 주세요.',
        'delivery_name': '🚚 배송 서비스',
        'delivery_info': '상품을 귀하의 주소로 배송해 드립니다.\n\n주문하려면 아래 버튼을 탭하세요 — 담당자가 연락드릴 것입니다.',
        'categories_label': '카테고리',
        'categories': {'electronics':'📱 전자제품','auto':'🚗 자동차','home':'🏠 생활용품',
                       'fruits':'🍎 과일','vegetables':'🥦 채소','kids':'👶 어린이용','clothes':'👗 의류','delivery':'🚚 배송'},
        'empty_category': '📭 아직 이 카테고리에 상품이 없습니다.'},
 'vi': {'choose_lang': 'Chọn ngôn ngữ của bạn:','lang_set': 'Đã chọn ngôn ngữ: Tiếng Việt ✅',
        'main_menu': 'Menu chính. Chọn một danh mục:','back': '⬅️ Quay lại','to_main': '🏠 Menu chính',
        'choose_product': 'Chọn một sản phẩm:','price': 'Giá','description': 'Mô tả',
        'buy_btn': '🛒 Mua','contact_btn': '📞 Liên hệ',
        'order_sent': '✅ Yêu cầu của bạn đã được nhận!\n\nSản phẩm: {name}\nGiá: {price}\n\nBạn có thể liên hệ trực tiếp với chúng tôi qua nút bên dưới.',
        'contact_link_text': '👉 Chạm để liên hệ','not_found': 'Vui lòng chọn một nút từ menu.',
        'delivery_name': '🚚 Dịch vụ giao hàng',
        'delivery_info': 'Chúng tôi giao sản phẩm đến địa chỉ của bạn.\n\nĐể đặt hàng, chạm vào nút bên dưới — nhân viên của chúng tôi sẽ liên hệ với bạn.',
        'categories_label': 'DANH MỤC',
        'categories': {'electronics':'📱 Điện tử','auto':'🚗 Ô tô','home':'🏠 Đồ gia dụng',
                       'fruits':'🍎 Trái cây','vegetables':'🥦 Rau củ','kids':'👶 Cho trẻ em','clothes':'👗 Quần áo','delivery':'🚚 Giao hàng'},
        'empty_category': '📭 Chưa có sản phẩm nào trong danh mục này.'}}

def t(lang: str, key: str, **kwargs) -> str:
    """Har qanday til uchun matnni qaytaradi."""
    txt = TEXTS.get(lang, TEXTS["en"]).get(key) or NEW_KEYS.get(lang, NEW_KEYS["en"]).get(key, key)
    return txt.format(**kwargs) if kwargs else txt

def nt(lang: str, key: str, **kwargs) -> str:
    """Yangi kalitlardan matnni qaytaradi."""
    txt = NEW_KEYS.get(lang, NEW_KEYS["en"]).get(key, key)
    return txt.format(**kwargs) if kwargs else txt
# ===========================================================================
# 3) FAYL OPERATSIYALARI
# ===========================================================================
DEFAULT_PRODUCTS = {"electronics":[],"auto":[],"home":[],"fruits":[],"vegetables":[],"kids":[],"clothes":[],"spare_parts":[],"food":[],"pharmacy":[]}

def _load_json(path, default):
    if not os.path.exists(path):
        _save_json(path, default)
        return json.loads(json.dumps(default))
    try:
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return json.loads(json.dumps(default))

def _save_json(path, data):
    with open(path,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_products() -> dict:
    data = _load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)
    for cat in DEFAULT_PRODUCTS:
        data.setdefault(cat, [])
    return data

def save_products(data): _save_json(PRODUCTS_FILE, data)

def load_orders() -> list:  return _load_json(ORDERS_FILE, [])
def save_orders(d): _save_json(ORDERS_FILE, d)

def load_users() -> dict: return _load_json(USERS_FILE, {})
def save_users(d): _save_json(USERS_FILE, d)

def load_reviews() -> list: return _load_json(REVIEWS_FILE, [])
def save_reviews(d): _save_json(REVIEWS_FILE, d)

def load_promos() -> dict: return _load_json(PROMOS_FILE, {})
def save_promos(d): _save_json(PROMOS_FILE, d)

def load_comments() -> list: return _load_json(COMMENTS_FILE, [])
def save_comments(d): _save_json(COMMENTS_FILE, d)

def load_faq() -> list: return _load_json(FAQ_FILE, [])
def save_faq(d): _save_json(FAQ_FILE, d)

def get_products() -> dict: return load_products()

# ---------------------------------------------------------------------------
# Foydalanuvchilar (+ referal maydonlari)
# ---------------------------------------------------------------------------
def register_user(user_id: int, full_name: str, username: str, referred_by: str = None):
    """Yangi foydalanuvchini ro'yxatga oladi. Agar referred_by berilgan bo'lsa va
    bu yangi foydalanuvchi bo'lsa, referal bog'lanishi saqlanadi.
    Qaytaradi: (is_new, did_register_referral)
    """
    users = load_users()
    uid = str(user_id)
    is_new = uid not in users
    if is_new:
        users[uid] = {
            "full_name": full_name,
            "username": username or "",
            "joined": datetime.now().isoformat(),
            "referred_by": None,
            "referral_count": 0,
            "referral_rewarded_for": [],   # qaysi referal user_idlari uchun bonus allaqachon berilgan
            "pending_discount": 0,         # promo ishlatilmagan чегирма (referal/promo)
            "cart_last_updated": None,     # eslatma uchun
            "cart_reminder_sent": False,
            "subscribed_new_products": True,
        }
        did_ref = False
        if referred_by and referred_by != uid and referred_by in users:
            users[uid]["referred_by"] = referred_by
            users[referred_by]["referral_count"] = users[referred_by].get("referral_count", 0) + 1
            users[uid]["pending_discount"] = REFERRAL_DISCOUNT_PERCENT
            did_ref = True
        save_users(users)
        return True, did_ref
    else:
        # mavjud bo'lsa ham yangi maydonlarni to'ldirib qo'yamiz (eski userlar uchun)
        changed = False
        defaults = {
            "referred_by": None, "referral_count": 0, "referral_rewarded_for": [],
            "pending_discount": 0, "cart_last_updated": None, "cart_reminder_sent": False,
            "subscribed_new_products": True,
        }
        for k, v in defaults.items():
            if k not in users[uid]:
                users[uid][k] = v
                changed = True
        if changed: save_users(users)
        return False, False

def get_user(user_id) -> dict:
    return load_users().get(str(user_id), {})

def touch_user_cart(user_id, has_items: bool):
    """Саватча holatini belgilaydi — eslatma yuborish uchun vaqt belgisi qo'yiladi."""
    users = load_users()
    uid = str(user_id)
    if uid not in users: return
    if has_items:
        users[uid]["cart_last_updated"] = datetime.now().isoformat()
        users[uid]["cart_reminder_sent"] = False
    else:
        users[uid]["cart_last_updated"] = None
        users[uid]["cart_reminder_sent"] = False
    save_users(users)

def mark_cart_reminder_sent(user_id):
    users = load_users()
    uid = str(user_id)
    if uid in users:
        users[uid]["cart_reminder_sent"] = True
        save_users(users)

def grant_referral_reward(referrer_id: str, code: str):
    users = load_users()
    if referrer_id in users:
        users[referrer_id]["pending_discount"] = REFERRAL_DISCOUNT_PERCENT
        save_users(users)

# ---------------------------------------------------------------------------
# Mahsulotlar (+ ko'p rasm)
# ---------------------------------------------------------------------------
def add_product(category, name, price, photos, description, qty=None):
    """photos — file_id lar ro'yxati (1 yoki bir nechta)."""
    if isinstance(photos, str):
        photos = [photos]
    data = load_products()
    new_id = f"{category[:2]}_{len(data[category])+1}_{os.urandom(2).hex()}"
    data[category].append({
        "id": new_id, "name": name, "price": price,
        "photos": photos, "description": description,
        "qty": qty,  # None = cheksiz
        "sold": 0,
        "low_stock_alerted": False,
    })
    save_products(data)
    return data[category][-1]

def create_order(user_id, user_name, username, items: list, discount=0, delivery_fee=0) -> str:
    orders = load_orders()
    order_id = str(len(orders) + 1)
    orders.append({
        "id": order_id,
        "user_id": str(user_id),
        "user_name": user_name,
        "username": username or "",
        "items": items,
        "discount": discount,
        "delivery_fee": round(delivery_fee, 1),
        "status": "new",
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
    })
    save_orders(orders)
    # sotilgan soni yangilash + kam qoldi tekshiruvi
    products = load_products()
    low_stock_products = []
    for item in items:
        for cat_items in products.values():
            for p in cat_items:
                if p["id"] == item.get("product_id"):
                    p["sold"] = p.get("sold", 0) + 1
                    if p.get("qty") is not None:
                        p["qty"] = max(0, p["qty"] - 1)
                        if p["qty"] <= LOW_STOCK_THRESHOLD and not p.get("low_stock_alerted"):
                            p["low_stock_alerted"] = True
                            low_stock_products.append(p)
                        elif p["qty"] > LOW_STOCK_THRESHOLD:
                            p["low_stock_alerted"] = False
    save_products(products)

    # referal bonusi: agar bu xaridorni kim taklif qilgan bo'lsa va u birinchi marta
    # buyurtma bersa — taklif qiluvchiga bonus beriladi
    users = load_users()
    uid = str(user_id)
    if uid in users:
        ref_by = users[uid].get("referred_by")
        if ref_by and uid not in users.get(ref_by, {}).get("referral_rewarded_for", []):
            user_orders_count = len([o for o in orders if o["user_id"] == uid])
            if user_orders_count >= REFERRAL_BONUS_AFTER_ORDERS and ref_by in users:
                users[ref_by].setdefault("referral_rewarded_for", []).append(uid)
                users[ref_by]["pending_discount"] = REFERRAL_DISCOUNT_PERCENT
                save_users(users)
                asyncio.create_task(_notify_referral_reward(ref_by))

        # --- SODIQLIK CHEGIRMASI: har 10 zakaz = keyingisida 10% чегирма ---
        user_orders_count = len([o for o in orders if o["user_id"] == uid])
        if user_orders_count % LOYALTY_ORDERS_COUNT == 0:
            users[uid]["pending_discount"] = LOYALTY_DISCOUNT_PERCENT
            save_users(users)
            asyncio.create_task(_notify_loyalty_reward(uid))

    return order_id, low_stock_products

async def _notify_referral_reward(referrer_id: str):
    users = load_users()
    u = users.get(referrer_id)
    if not u: return
    lang = u.get("lang", "uz")
    code = f"REF{referrer_id}"
    # avtomatik promo-kod yaratib qo'yamiz
    promos = load_promos()
    promos[code] = {"discount": REFERRAL_DISCOUNT_PERCENT, "referral": True}
    save_promos(promos)
    try:
        await bot.send_message(int(referrer_id), nt(lang, "referral_reward", discount=REFERRAL_DISCOUNT_PERCENT, code=code))
    except Exception as e:
        logger.error(e)

async def _notify_loyalty_reward(user_id: str):
    """Xaridorga 10 zakaz to'lgani uchun чегирма promo-kod yuboradi."""
    users = load_users()
    u = users.get(user_id)
    if not u: return
    lang = u.get("lang", "uz")
    code = f"LOYAL{user_id}"
    promos = load_promos()
    promos[code] = {"discount": LOYALTY_DISCOUNT_PERCENT, "loyalty": True}
    save_promos(promos)
    msgs = {
        "uz": (f"🎉 Табрикlaymiz! Сиз {LOYALTY_ORDERS_COUNT} та заказ бердингиз!\n\n"
               f"🎁 Кейинги заказингизда <b>{LOYALTY_DISCOUNT_PERCENT}% чегирма</b> sovg'a!\n\n"
               f"Промо-код: <code>{code}</code>\n"
               f'Заказда "Промо-код" бўлимига киритинг.'),
        "ru": (f"🎉 Поздравляем! Вы сделали {LOYALTY_ORDERS_COUNT} заказов!\n\n"
               f"🎁 На следующий заказ скидка <b>{LOYALTY_DISCOUNT_PERCENT}%</b>!\n\n"
               f"Промо-код: <code>{code}</code>"),
        "en": (f"🎉 Congratulations! You've placed {LOYALTY_ORDERS_COUNT} orders!\n\n"
               f"🎁 Here's <b>{LOYALTY_DISCOUNT_PERCENT}% off</b> your next order!\n\n"
               f"Promo code: <code>{code}</code>"),
    }
    text = msgs.get(lang, msgs["uz"])
    try:
        await bot.send_message(int(user_id), text, parse_mode="HTML")
    except Exception as e:
        logger.error(e)

def get_user_orders(user_id: int) -> list:
    orders = load_orders()
    return [o for o in orders if o["user_id"] == str(user_id)]

def get_order_by_id(order_id: str):
    for o in load_orders():
        if o["id"] == str(order_id):
            return o
    return None

def check_promo(code: str):
    promos = load_promos()
    return promos.get(code.strip().upper())

# ---------------------------------------------------------------------------
# Izohlar (matnli, moderatsiyali)
# ---------------------------------------------------------------------------
def add_comment(product_id, user_id, user_name, text):
    comments = load_comments()
    cid = str(len(comments) + 1)
    comments.append({
        "id": cid, "product_id": product_id, "user_id": str(user_id),
        "user_name": user_name, "text": text, "status": "pending",  # pending/approved/rejected
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
    })
    save_comments(comments)
    return cid

def get_approved_comments(product_id):
    return [c for c in load_comments() if c["product_id"] == product_id and c["status"] == "approved"]

def get_pending_comments():
    return [c for c in load_comments() if c["status"] == "pending"]

def set_comment_status(comment_id, status):
    comments = load_comments()
    found = None
    for c in comments:
        if c["id"] == str(comment_id):
            c["status"] = status
            found = c
            break
    save_comments(comments)
    return found

# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------
def add_faq(question, answer):
    faqs = load_faq()
    fid = str(len(faqs) + 1)
    faqs.append({"id": fid, "question": question, "answer": answer})
    save_faq(faqs)
    return fid

def delete_faq(fid):
    faqs = load_faq()
    faqs = [f for f in faqs if f["id"] != str(fid)]
    save_faq(faqs)
# ===========================================================================
# 4) FSM HOLATLARI
# ===========================================================================
class UserState(StatesGroup):
    choosing_language = State()
    in_main_menu      = State()
    in_category       = State()
    viewing_product   = State()
    in_delivery       = State()
    in_cart           = State()
    searching         = State()
    entering_promo    = State()
    viewing_referral  = State()
    entering_comment  = State()
    viewing_faq       = State()
    waiting_location  = State()   # yetkazib berish narxini hisoblash uchun lokatsiya kutilmoqda

class AdminState(StatesGroup):
    menu                 = State()
    add_choosing_category= State()
    add_name             = State()
    add_price            = State()
    add_qty              = State()
    add_photo            = State()       # endi bir nechta rasm qabul qiladi
    add_description      = State()
    edit_choosing        = State()
    edit_field           = State()
    edit_value           = State()
    delete_choosing      = State()
    manage_order_id      = State()
    manage_order_status  = State()
    broadcast_text       = State()
    add_promo_code       = State()
    add_promo_discount   = State()
    moderating_comments  = State()
    add_faq_question     = State()
    add_faq_answer       = State()
    delete_faq_choosing  = State()
    viewing_top_customers= State()
    set_delivery_time    = State()   # yetkazish vaqtini belgilash
    manage_discount      = State()   # чегирмаni boshqarish

CATEGORY_KEYS = ["electronics","auto","home","fruits","vegetables","kids","clothes","spare_parts","food","pharmacy"]
# ===========================================================================
# 5) YORDAMCHI FUNKSIYALAR — KLAVIATURALAR
# ===========================================================================
def is_admin(uid): return ADMIN_IDS and str(uid) in ADMIN_IDS

def get_language_keyboard():
    names = list(LANG_BUTTONS.keys())
    rows  = [names[i:i+2] for i in range(0, len(names), 2)]
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=n) for n in r] for r in rows], resize_keyboard=True)

def get_categories_keyboard(lang, user_id=0):
    cats = TEXTS[lang]["categories"]
    rows = [
        [KeyboardButton(text=cats["electronics"]), KeyboardButton(text=cats["auto"])],
        [KeyboardButton(text=cats["home"]),         KeyboardButton(text=cats["fruits"])],
        [KeyboardButton(text=cats["vegetables"]),   KeyboardButton(text=cats["kids"])],
        [KeyboardButton(text=cats["clothes"]),      KeyboardButton(text=cats["spare_parts"])],
        [KeyboardButton(text=cats["food"]),         KeyboardButton(text=cats["pharmacy"])],
        [KeyboardButton(text=cats["delivery"])],
        [KeyboardButton(text=nt(lang,"search")), KeyboardButton(text=nt(lang,"cart"))],
        [KeyboardButton(text=nt(lang,"my_orders")), KeyboardButton(text=nt(lang,"referral_btn"))],
        [KeyboardButton(text=nt(lang,"faq_btn"))],
    ]
    if is_admin(user_id):
        rows.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def get_category_products_keyboard(lang, category):
    products = get_products()
    names    = [p["name"] for p in products.get(category, [])]
    rows     = [names[i:i+2] for i in range(0, len(names), 2)]
    keyboard = [[KeyboardButton(text=n) for n in r] for r in rows]
    keyboard.append([KeyboardButton(text=t(lang,"to_main"))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_product_keyboard(lang):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang,"buy_btn")), KeyboardButton(text=nt(lang,"cart"))],
        [KeyboardButton(text=nt(lang,"rate_btn")), KeyboardButton(text=nt(lang,"comment_btn"))],
        [KeyboardButton(text=nt(lang,"promo_btn"))],
        [KeyboardButton(text=t(lang,"back")),    KeyboardButton(text=t(lang,"to_main"))],
    ], resize_keyboard=True)

def get_cart_keyboard(lang):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=nt(lang,"cart_order"))],
        [KeyboardButton(text=nt(lang,"delivery_location_btn"), request_location=True)],
        [KeyboardButton(text=nt(lang,"cart_clear"))],
        [KeyboardButton(text=t(lang,"to_main"))],
    ], resize_keyboard=True)

def get_delivery_keyboard(lang):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(lang,"contact_btn"))],
        [KeyboardButton(text=t(lang,"to_main"))],
    ], resize_keyboard=True)

def get_contact_inline_keyboard(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Админ билан боғланиш ✍️", url=ADMIN_CONTACT_LINK)],
    ])

def rating_inline_keyboard(product_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{i}⭐", callback_data=f"rate_{product_id}_{i}") for i in range(1,6)
    ]])

def order_status_inline(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Qabul qilindi",  callback_data=f"ostatus_{order_id}_accepted"),
        InlineKeyboardButton(text="🚚 Yetkazildi",     callback_data=f"ostatus_{order_id}_delivered"),
        InlineKeyboardButton(text="❌ Bekor qilish",   callback_data=f"ostatus_{order_id}_cancelled"),
    ]])

def photo_carousel_keyboard(lang, product_id, current, total):
    buttons = []
    if total > 1:
        nav = []
        if current > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"photonav_{product_id}_{current-1}"))
        nav.append(InlineKeyboardButton(text=nt(lang,"photo_more",current=current+1,total=total), callback_data="noop"))
        if current < total - 1:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"photonav_{product_id}_{current+1}"))
        buttons.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

def comment_moderation_inline(comment_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"cmtok_{comment_id}"),
        InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"cmtno_{comment_id}"),
    ]])

def find_category_by_button_text(lang, text):
    cats = TEXTS[lang]["categories"]
    for key, label in cats.items():
        if label == text and key != "delivery":
            return key
    return None

def is_delivery_button(lang, text): return text == TEXTS[lang]["categories"]["delivery"]
def all_to_main_texts():  return [TEXTS[l]["to_main"] for l in TEXTS]
def all_back_texts():     return [TEXTS[l]["back"] for l in TEXTS]
def all_buy_texts():      return [TEXTS[l]["buy_btn"] for l in TEXTS]
def all_contact_texts():  return [TEXTS[l]["contact_btn"] for l in TEXTS]
def all_cart_texts():     return list({nt(l,"cart") for l in LANG_BUTTONS.values()})
def all_search_texts():   return list({nt(l,"search") for l in LANG_BUTTONS.values()})
def all_myorders_texts(): return list({nt(l,"my_orders") for l in LANG_BUTTONS.values()})
def all_ratebtn_texts():  return list({nt(l,"rate_btn") for l in LANG_BUTTONS.values()})
def all_promobtn_texts(): return list({nt(l,"promo_btn") for l in LANG_BUTTONS.values()})
def all_cartorder_texts():return list({nt(l,"cart_order") for l in LANG_BUTTONS.values()})
def all_cartclear_texts():return list({nt(l,"cart_clear") for l in LANG_BUTTONS.values()})
def all_referral_texts(): return list({nt(l,"referral_btn") for l in LANG_BUTTONS.values()})
def all_comment_texts():  return list({nt(l,"comment_btn") for l in LANG_BUTTONS.values()})
def all_faq_texts():      return list({nt(l,"faq_btn") for l in LANG_BUTTONS.values()})

CATEGORY_LABELS_UZ = {
    "electronics":"📱 Elektronika","auto":"🚗 Mashina",
    "home":"🏠 Uy-xo'jalik","fruits":"🍎 Mevalar","vegetables":"🥦 Sabzavotlar",
    "kids":"👶 Bolalar uchun","clothes":"🛍️ Kiyim-kechaklar","spare_parts":"🔧 Zapchastlar","food":"🍽️ Oziq-ovqat","pharmacy":"💊 Dorixona/gigiyena",
}

def admin_menu_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Mahsulot qo'shish"), KeyboardButton(text="📋 Mahsulotlar ro'yxati")],
        [KeyboardButton(text="✏️ Mahsulotni tahrirlash"), KeyboardButton(text="🗑 Mahsulotni o'chirish")],
        [KeyboardButton(text="📦 Buyurtmalar"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📢 Ommaviy xabar"), KeyboardButton(text="🎟 Promo-kod qo'shish")],
        [KeyboardButton(text="💰 Chegirmalarni boshqarish")],
        [KeyboardButton(text="📤 Eksport (CSV)"), KeyboardButton(text="👥 Top mijozlar")],
        [KeyboardButton(text="💬 Izohlarni moderatsiya"), KeyboardButton(text="❓ FAQ boshqarish")],
        [KeyboardButton(text="🚪 Admin rejimidan chiqish")],
    ], resize_keyboard=True)

def admin_category_keyboard():
    labels = list(CATEGORY_LABELS_UZ.values())
    rows   = [labels[i:i+2] for i in range(0, len(labels), 2)]
    kb     = [[KeyboardButton(text=l) for l in r] for r in rows]
    kb.append([KeyboardButton(text="❌ Bekor qilish")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

def admin_photo_done_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Rasmlar tayyor")],
        [KeyboardButton(text="❌ Bekor qilish")],
    ], resize_keyboard=True)

def find_category_key_by_uz_label(text):
    for k, v in CATEGORY_LABELS_UZ.items():
        if v == text: return k
    return None

def find_product_by_name(category, name):
    for p in get_products().get(category, []):
        if p["name"] == name: return p
    return None

def find_product_by_id(pid):
    for cat_items in get_products().values():
        for p in cat_items:
            if p["id"] == pid: return p
    return None

def find_product_category(pid):
    for cat, items in get_products().items():
        for p in items:
            if p["id"] == pid: return cat
    return None

# ---------------------------------------------------------------------------
# YETKAZIB BERISH NARXI HISOBLASH
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Ikki koordinata orasidagi masofani km da hisoblaydi (Haversine formula)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def save_admin_location(lat: float, lon: float):
    """Adminning joriy lokatsiyasini faylga saqlaydi."""
    with open(ADMIN_LOCATION_FILE, "w", encoding="utf-8") as f:
        json.dump({"lat": lat, "lon": lon, "updated": datetime.now().isoformat()}, f)

def load_admin_location():
    """Saqlangan admin lokatsiyasini qaytaradi. Fayl yo'q bo'lsa — standart koordinata."""
    if os.path.exists(ADMIN_LOCATION_FILE):
        try:
            with open(ADMIN_LOCATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"lat": DEFAULT_ADMIN_LATITUDE, "lon": DEFAULT_ADMIN_LONGITUDE}

def calc_delivery_price(admin_lat: float, admin_lon: float, user_lat: float, user_lon: float) -> dict:
    """
    Admin va xaridor koordinatasi asosida yetkazib berish narxini hisoblaydi.
    Qaytaradi: {'km': float, 'base': int, 'km_price': float, 'delivery': float}
    """
    km = haversine_km(admin_lat, admin_lon, user_lat, user_lon)
    km_price = km * DELIVERY_PRICE_PER_KM
    delivery = DELIVERY_BASE_PRICE + km_price
    return {
        "km": km,
        "base": DELIVERY_BASE_PRICE,
        "km_price": km_price,
        "delivery": delivery,
        "currency": DELIVERY_CURRENCY,
    }

def product_qty_text(lang, product):
    qty = product.get("qty")
    if qty is None: return ""
    if qty == 0: return f"\n{nt(lang,'out_of_stock')}"
    return f"\n{nt(lang,'qty_left',qty=qty)}"

def get_product_photos(product):
    """Eski formatdagi ('photo') va yangi formatdagi ('photos') mahsulotlarni qo'llab-quvvatlaydi."""
    if "photos" in product and product["photos"]:
        return product["photos"]
    if "photo" in product and product["photo"]:
        return [product["photo"]]
    return []

def build_product_caption(lang, product):
    avg     = _avg_rating(product["id"])
    stars   = f"  {'⭐'*round(avg)} ({avg:.1f})" if avg else ""
    qty_txt = product_qty_text(lang, product)
    return (f"<b>{product['name']}</b>{stars}\n\n"
            f"{t(lang,'price')}: {product['price']}{qty_txt}\n\n"
            f"{t(lang,'description')}: {product['description']}")
# ===========================================================================
# 6) XARIDOR HANDLERLARI
# ===========================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # /start REF12345 — referal orqali kelgan foydalanuvchini aniqlash
    args = message.text.split(maxsplit=1)
    referred_by = None
    if len(args) > 1:
        arg = args[1].strip()
        if arg.startswith("ref"):
            candidate = arg[3:]
            if candidate.isdigit():
                referred_by = candidate

    is_new, did_ref = register_user(
        message.from_user.id, message.from_user.full_name, message.from_user.username, referred_by
    )
    await state.set_state(UserState.choosing_language)
    await message.answer("Tilni tanlang / Choose language / Выберите язык:", reply_markup=get_language_keyboard())
    if did_ref:
        await state.update_data(_just_referred=True)

@dp.message(UserState.choosing_language, F.text.in_(LANG_BUTTONS.keys()))
async def process_language(message: Message, state: FSMContext):
    lang = LANG_BUTTONS[message.text]
    data = await state.get_data()
    await state.update_data(lang=lang, cart=[])
    await state.set_state(UserState.in_main_menu)

    # foydalanuvchining tilini saqlab qo'yamiz (xabarlar/eslatmalar uchun kerak)
    users = load_users()
    uid = str(message.from_user.id)
    if uid in users:
        users[uid]["lang"] = lang
        save_users(users)

    await message.answer(t(lang,"lang_set"))

    if data.get("_just_referred"):
        await message.answer(nt(lang, "referral_welcome", discount=REFERRAL_DISCOUNT_PERCENT))
        await state.update_data(promo_discount=REFERRAL_DISCOUNT_PERCENT)

    await message.answer(t(lang,"main_menu"), reply_markup=get_categories_keyboard(lang, message.from_user.id))

# --- Buyurtmani kuzatish: /order_5 ---
@dp.message(F.text.regexp(r"^/order_(\d+)$"))
async def track_order(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang") or get_user(message.from_user.id).get("lang", "uz")
    order_id = message.text.split("_", 1)[1]
    order = get_order_by_id(order_id)
    if not order or order["user_id"] != str(message.from_user.id):
        await message.answer(nt(lang, "order_track_not_found")); return
    status_map = {
        "new": nt(lang,"order_status_new"), "accepted": nt(lang,"order_status_accepted"),
        "delivered": nt(lang,"order_status_delivered"), "cancelled": nt(lang,"order_status_cancelled"),
    }
    items_str = ", ".join(i["name"] for i in order["items"])
    await message.answer(
        nt(lang,"order_item", id=order["id"], name=items_str, price="—",
           status=status_map.get(order["status"], order["status"]), date=order["date"])
    )

@dp.message(Command("order"))
async def track_order_usage(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang") or get_user(message.from_user.id).get("lang", "uz")
    await message.answer(nt(lang, "order_track_usage"))

# --- "Bosh menyu" tugmasi ---
async def go_main(message, state, lang):
    await state.set_state(UserState.in_main_menu)
    await message.answer(t(lang,"main_menu"), reply_markup=get_categories_keyboard(lang, message.from_user.id))

@dp.message(F.text.in_(all_to_main_texts()))
async def process_to_main(message: Message, state: FSMContext):
    data = await state.get_data()
    await go_main(message, state, data.get("lang","uz"))

# --- Referal bo'limi ---
@dp.message(F.text.in_(all_referral_texts()))
async def show_referral(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    user = get_user(message.from_user.id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref{message.from_user.id}"
    count = user.get("referral_count", 0)
    await message.answer(nt(lang,"referral_info", discount=REFERRAL_DISCOUNT_PERCENT, link=link, count=count))

# --- FAQ bo'limi ---
@dp.message(F.text.in_(all_faq_texts()))
async def show_faq(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    faqs = load_faq()
    if not faqs:
        await message.answer(nt(lang,"faq_empty")); return
    lines = [nt(lang,"faq_title"), ""]
    for i, f in enumerate(faqs, 1):
        lines.append(f"{i}. <b>{f['question']}</b>\n{f['answer']}\n")
    await message.answer("\n".join(lines), parse_mode="HTML")

# --- Qidiruv ---
@dp.message(F.text.in_(all_search_texts()))
async def start_search(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    await state.set_state(UserState.searching)
    await message.answer(nt(lang,"search_prompt"), reply_markup=admin_cancel_keyboard())

@dp.message(UserState.searching)
async def do_search(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    if message.text == "❌ Bekor qilish":
        await go_main(message, state, lang); return
    query = message.text.lower()
    results = []
    for cat, items in get_products().items():
        for p in items:
            if query in p["name"].lower() or query in p.get("description","").lower():
                results.append((cat, p))
    if not results:
        await message.answer(nt(lang,"search_no_result")); return
    for cat, p in results[:10]:
        caption = build_product_caption(lang, p)
        photos = get_product_photos(p)
        if photos:
            await message.answer_photo(photo=photos[0], caption=caption, parse_mode="HTML")
        else:
            await message.answer(caption, parse_mode="HTML")
    await state.set_state(UserState.in_main_menu)
    await message.answer(t(lang,"main_menu"), reply_markup=get_categories_keyboard(lang, message.from_user.id))
# --- Саватча ---
@dp.message(F.text.in_(all_cart_texts()))
async def show_cart(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    cart = data.get("cart", [])
    if not cart:
        await message.answer(nt(lang,"cart_empty")); return
    lines = [f"{i+1}. {nt(lang,'cart_item',name=item['name'],price=item['price'])}" for i, item in enumerate(cart)]
    lines.append(f"\n{nt(lang,'cart_total',count=len(cart))}")

    # Jami summa hisoblash (faqat raqamli narxlar)
    total = 0
    currency_symbol = ""
    for item in cart:
        price_str = item.get("price","")
        import re
        nums = re.findall(r'[\d]+', price_str.replace(" ",""))
        if nums:
            total += int(nums[0])
            if not currency_symbol:
                currency_symbol = re.sub(r'[\d\s]', '', price_str).strip()
    delivery_fee = (await state.get_data()).get("delivery_fee", 0)
    if total > 0:
        lines.append(f"\n💰 Маҳсулотлар жами: {total} {currency_symbol}")
        if delivery_fee > 0:
            lines.append(f"🚚 Yetkazib berish: {delivery_fee:.0f} {DELIVERY_CURRENCY}")
            lines.append(f"✅ Umumiy jami: {total + delivery_fee:.0f} {DELIVERY_CURRENCY if not currency_symbol else currency_symbol}")
        else:
            lines.append(f"📍 Жойлашувингизни юборинг → етказиб бериш нархи қўшилади")

    await state.set_state(UserState.in_cart)
    await message.answer("\n".join(lines), reply_markup=get_cart_keyboard(lang))

@dp.message(UserState.in_cart, F.text.in_(all_cartorder_texts()))
async def cart_place_order(message: Message, state: FSMContext):
    data  = await state.get_data()
    lang  = data.get("lang","uz")
    cart  = data.get("cart",[])
    disc  = data.get("promo_discount", 0)
    delivery_fee = data.get("delivery_fee", 0)
    if not cart:
        await message.answer(nt(lang,"cart_empty")); return
    # Lokatsiya majburiy — avval joylashuvni yuboring
    if not data.get("user_lat"):
        await message.answer(
            "📍 Буюртма беришдан олдин жойлашувингизни юборинг!",
            reply_markup=get_cart_keyboard(lang)
        ); return
    user  = message.from_user
    oid, low_stock = create_order(user.id, user.full_name, user.username, cart, discount=disc, delivery_fee=delivery_fee)
    names = ", ".join(i["name"] for i in cart)

    # Xaridorga buyurtma kodi ko'rsatish
    order_code = f"#{oid}"
    order_text = (
        f"✅ Буюртмангиз қабул қилинди!\n\n"
        f"🧾 Буюртма кодингиз: <b>{order_code}</b>\n"
        f"📦 Маҳсулот: {names}\n"
    )
    if delivery_fee > 0:
        order_text += f"🚚 Yetkazib berish: {delivery_fee:.0f} {DELIVERY_CURRENCY}\n"
    order_text += (
        f"\n⏳ Админ тасдиқлашини кутинг.\n"
        f"📞 Савол бўлса қуйидаги тугма орқали боғланинг."
    )
    await message.answer(order_text, parse_mode="HTML", reply_markup=get_contact_inline_keyboard(lang))
    await state.update_data(cart=[], promo_discount=0, delivery_fee=0)
    touch_user_cart(user.id, has_items=False)
    user_lat = data.get("user_lat")
    user_lon = data.get("user_lon")
    await notify_admin_cart_order(user, cart, oid, disc, delivery_fee=delivery_fee, user_lat=user_lat, user_lon=user_lon)

    # kam qolgan mahsulotlar haqida adminga va xaridorga ogohlantirish
    for p in low_stock:
        await notify_admin_low_stock(p)
    if low_stock:
        for p in low_stock:
            try:
                await message.answer(nt(lang, "low_stock_user_warning", name=p["name"], qty=p["qty"]))
            except Exception:
                pass

    await go_main(message, state, lang)

@dp.message(UserState.in_cart, F.text.in_(all_cartclear_texts()))
async def cart_clear(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    await state.update_data(cart=[], delivery_fee=0)
    touch_user_cart(message.from_user.id, has_items=False)
    await go_main(message, state, lang)

# --- Lokatsiya orqali yetkazib berish narxini hisoblash ---
@dp.message(UserState.in_cart, F.location)
async def cart_location_received(message: Message, state: FSMContext):
    """Xaridor lokatsiya yuborganda — darhol joriy admin koordinatasidan hisoblaydi."""
    data = await state.get_data()
    lang = data.get("lang","uz")
    cart = data.get("cart", [])

    user_lat = message.location.latitude
    user_lon = message.location.longitude
    await state.update_data(user_lat=user_lat, user_lon=user_lon)

    # Joriy admin lokatsiyasini olamiz (fayl yo'q bo'lsa standart koordinata)
    admin_loc = load_admin_location()
    result = calc_delivery_price(admin_loc["lat"], admin_loc["lon"], user_lat, user_lon)

    products_total_str = " + ".join(i["price"] for i in cart) if cart else "—"
    delivery_fee = result["delivery"]
    await state.update_data(delivery_fee=delivery_fee)

    text = nt(lang, "delivery_price_result",
        km=result["km"],
        base=result["base"],
        km_price=result["km_price"],
        delivery=delivery_fee,
        currency=result["currency"],
        products_total=products_total_str,
        grand_total=f"{delivery_fee:.0f} {result['currency']} + mahsulotlar",
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_cart_keyboard(lang))

    # Adminga ham xabar yuboramiz (ma'lumot uchun)
    user = message.from_user
    cart_names = ", ".join(i["name"] for i in cart)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                int(admin_id),
                f"📍 Yetkazib berish so'rovi\n\n"
                f"Xaridor: {user.full_name} (@{user.username or '—'})\n"
                f"Masofa: ~{result['km']:.1f} km\n"
                f"Yetkazib berish: {delivery_fee:.0f} {DELIVERY_CURRENCY}\n"
                f"Саватча: {cart_names}"
            )
        except Exception as e:
            logger.error(f"Admin xabarnomasi xatosi: {e}")


@dp.message(F.location)
async def admin_location_received(message: Message, state: FSMContext):
    """Admin lokatsiyasini yuborganda — barcha kutayotgan xaridorlar uchun masofa hisoblanadi."""
    if not is_admin(message.from_user.id):
        return

    admin_lat = message.location.latitude
    admin_lon = message.location.longitude
    save_admin_location(admin_lat, admin_lon)

    if not _pending_delivery:
        await message.answer(
            f"✅ Lokatsiyangiz saqlandi ({admin_lat:.4f}, {admin_lon:.4f}).\nHozircha kutayotgan xaridor yo'q.",
            reply_markup=admin_menu_keyboard()
        )
        return

    # Barcha kutayotgan xaridorlar uchun hisoblash
    processed = []
    for uid, info in list(_pending_delivery.items()):
        result = calc_delivery_price(admin_lat, admin_lon, info["user_lat"], info["user_lon"])
        lang = info["lang"]
        cart = info["cart"]
        products_total_str = " + ".join(i["price"] for i in cart)

        text = nt(lang, "delivery_price_result",
            km=result["km"],
            base=result["base"],
            km_price=result["km_price"],
            delivery=result["delivery"],
            currency=result["currency"],
            products_total=products_total_str,
            grand_total=f"{result['delivery']:.0f} {result['currency']} + mahsulotlar",
        )
        try:
            await bot.send_message(int(uid), text, parse_mode="HTML")
            processed.append(uid)
        except Exception as e:
            logger.error(f"Xaridorga natija yuborishda xato {uid}: {e}")

    # Ishlangan so'rovlarni o'chiramiz
    for uid in processed:
        _pending_delivery.pop(uid, None)

    await message.answer(
        f"✅ {len(processed)} ta xaridorga yetkazib berish narxi yuborildi.",
        reply_markup=admin_menu_keyboard()
    )

# --- Buyurtmalarim ---
@dp.message(F.text.in_(all_myorders_texts()))
async def my_orders(message: Message, state: FSMContext):
    data   = await state.get_data()
    lang   = data.get("lang","uz")
    orders = get_user_orders(message.from_user.id)
    if not orders:
        await message.answer(nt(lang,"no_orders")); return
    status_map = {
        "new":nt(lang,"order_status_new"),"accepted":nt(lang,"order_status_accepted"),
        "delivered":nt(lang,"order_status_delivered"),"cancelled":nt(lang,"order_status_cancelled"),
    }
    lines = []
    for o in orders[-10:]:
        items_str = ", ".join(i["name"] for i in o["items"])
        lines.append(nt(lang,"order_item",id=o["id"],name=items_str,price="—",status=status_map.get(o["status"],o["status"]),date=o["date"]))
    lines.append("\n" + nt(lang, "order_track_usage"))
    await message.answer("\n".join(lines))

# --- Baholash tugmasi ---
@dp.message(F.text.in_(all_ratebtn_texts()))
async def rate_product_btn(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    pid  = data.get("product_id")
    if not pid:
        await message.answer(t(lang,"not_found")); return
    await message.answer(nt(lang,"rate_prompt"), reply_markup=rating_inline_keyboard(pid))

@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(cb: CallbackQuery, state: FSMContext):
    # cb.data = "rate_{product_id}_{stars}"
    # product_id o'z ichida "_" bo'lishi mumkin, shuning uchun oxiridan ajratamiz
    parts = cb.data.split("_")
    stars = parts[-1]          # oxirgi qism — yulduz soni
    pid   = "_".join(parts[1:-1])  # o'rtadagi qismlar — product_id
    try:
        stars_int = int(stars)
    except ValueError:
        await cb.answer("Xato"); return
    reviews = load_reviews()
    reviews.append({"product_id": pid, "user_id": str(cb.from_user.id), "stars": stars_int, "date": datetime.now().isoformat()})
    save_reviews(reviews)
    fsm_data = await state.get_data()
    lang = fsm_data.get("lang","uz")
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer(nt(lang,"rate_thanks",stars="⭐"*stars_int))

def _avg_rating(product_id):
    reviews = [r for r in load_reviews() if r["product_id"] == product_id]
    if not reviews: return 0
    return sum(r["stars"] for r in reviews) / len(reviews)

# --- Izoh (отзыв) qoldirish ---
@dp.message(F.text.in_(all_comment_texts()))
async def comment_btn(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    pid  = data.get("product_id")
    if not pid:
        await message.answer(t(lang,"not_found")); return
    await state.set_state(UserState.entering_comment)
    await message.answer(nt(lang,"comment_prompt"), reply_markup=admin_cancel_keyboard())

@dp.message(UserState.entering_comment)
async def process_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    pid  = data.get("product_id")
    if message.text == "❌ Bekor qilish":
        await state.set_state(UserState.viewing_product)
        await message.answer("❌", reply_markup=get_product_keyboard(lang)); return
    cid = add_comment(pid, message.from_user.id, message.from_user.full_name, message.text)
    await state.set_state(UserState.viewing_product)
    await message.answer(nt(lang,"comment_thanks"), reply_markup=get_product_keyboard(lang))
    await notify_admin_new_comment(message.from_user, pid, cid, message.text)

# --- Promo kod ---
@dp.message(F.text.in_(all_promobtn_texts()))
async def promo_btn(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    await state.set_state(UserState.entering_promo)
    await message.answer(nt(lang,"promo_prompt"), reply_markup=admin_cancel_keyboard())

@dp.message(UserState.entering_promo)
async def process_promo(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    if message.text == "❌ Bekor qilish":
        await state.set_state(UserState.viewing_product)
        await message.answer("❌", reply_markup=get_product_keyboard(lang)); return
    promo = check_promo(message.text)
    if not promo:
        await message.answer(nt(lang,"promo_invalid")); return
    disc = promo["discount"]
    await state.update_data(promo_discount=disc)
    await state.set_state(UserState.viewing_product)
    await message.answer(nt(lang,"promo_used",discount=disc))
# --- Asosiy menyu tanlovi ---
@dp.message(UserState.in_main_menu)
async def process_main_menu_choice(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")

    if message.text == "🛠 Admin panel" and is_admin(message.from_user.id):
        await state.set_state(AdminState.menu)
        await message.answer("🛠 Admin panel:", reply_markup=admin_menu_keyboard()); return

    if is_delivery_button(lang, message.text):
        await state.set_state(UserState.in_delivery)
        await message.answer(f"{t(lang,'delivery_name')}\n\n{t(lang,'delivery_info')}", reply_markup=get_delivery_keyboard(lang)); return

    category = find_category_by_button_text(lang, message.text)
    if not category:
        await message.answer(t(lang,"not_found"), reply_markup=get_categories_keyboard(lang, message.from_user.id)); return

    products = get_products()
    if not products.get(category):
        await message.answer(t(lang,"empty_category"), reply_markup=get_categories_keyboard(lang, message.from_user.id)); return

    await state.update_data(category=category)
    await state.set_state(UserState.in_category)
    await message.answer(t(lang,"choose_product"), reply_markup=get_category_products_keyboard(lang, category))

# --- Kategoriya ichida mahsulot ---
@dp.message(UserState.in_category, F.text.in_(all_back_texts()))
async def back_to_main_from_category(message: Message, state: FSMContext):
    data = await state.get_data()
    await go_main(message, state, data.get("lang","uz"))

async def _show_comments_for_product(message_or_cb_message, lang, product_id):
    comments = get_approved_comments(product_id)
    if not comments:
        return
    lines = [nt(lang, "comments_label")]
    for c in comments[-5:]:
        lines.append(f"👤 {c['user_name']}: {c['text']}")
    await message_or_cb_message.answer("\n".join(lines))

@dp.message(UserState.in_category)
async def process_show_product(message: Message, state: FSMContext):
    data     = await state.get_data()
    lang     = data.get("lang","uz")
    category = data.get("category")
    product  = find_product_by_name(category, message.text)
    if not product:
        await message.answer(t(lang,"not_found"), reply_markup=get_category_products_keyboard(lang, category)); return

    qty = product.get("qty")
    if qty is not None and qty == 0:
        await message.answer(nt(lang,"out_of_stock")); return

    await state.update_data(product_id=product["id"], photo_index=0)
    await state.set_state(UserState.viewing_product)

    caption = build_product_caption(lang, product)
    photos  = get_product_photos(product)
    if photos:
        kb = photo_carousel_keyboard(lang, product["id"], 0, len(photos))
        sent = await message.answer_photo(photo=photos[0], caption=caption, parse_mode="HTML", reply_markup=kb)
        await state.update_data(carousel_msg_id=sent.message_id)
    else:
        await message.answer(caption, parse_mode="HTML")

    await message.answer("⬇️", reply_markup=get_product_keyboard(lang))
    await _show_comments_for_product(message, lang, product["id"])

# --- Rasm-karuselda navigatsiya ---
@dp.callback_query(F.data.startswith("photonav_"))
async def photo_navigate(cb: CallbackQuery, state: FSMContext):
    _, pid, idx = cb.data.split("_")
    idx = int(idx)
    product = find_product_by_id(pid)
    if not product:
        await cb.answer("Topilmadi"); return
    photos = get_product_photos(product)
    if idx < 0 or idx >= len(photos):
        await cb.answer(); return
    data = await state.get_data()
    lang = data.get("lang","uz")
    kb = photo_carousel_keyboard(lang, pid, idx, len(photos))
    try:
        from aiogram.types import InputMediaPhoto
        await cb.message.edit_media(media=InputMediaPhoto(media=photos[idx], caption=cb.message.caption, parse_mode="HTML"), reply_markup=kb)
    except Exception as e:
        logger.error(e)
    await state.update_data(photo_index=idx)
    await cb.answer()

@dp.callback_query(F.data == "noop")
async def noop_cb(cb: CallbackQuery):
    await cb.answer()

# --- Mahsulot sahifasida "Orqaga" ---
@dp.message(UserState.viewing_product, F.text.in_(all_back_texts()))
async def back_to_category(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    category = data.get("category")
    await state.set_state(UserState.in_category)
    await message.answer(t(lang,"choose_product"), reply_markup=get_category_products_keyboard(lang, category))

# --- Sotib olish (savatchaga qo'shish) ---
@dp.message(UserState.viewing_product, F.text.in_(all_buy_texts()))
async def process_buy(message: Message, state: FSMContext):
    data    = await state.get_data()
    lang    = data.get("lang","uz")
    cat     = data.get("category")
    pid     = data.get("product_id")
    product = find_product_by_id(pid)
    if not product:
        await message.answer(t(lang,"not_found")); return

    cart = data.get("cart", [])
    cart.append({"product_id": product["id"], "name": product["name"], "price": product["price"], "category": cat})
    await state.update_data(cart=cart)
    touch_user_cart(message.from_user.id, has_items=True)
    touch_user_cart_items(message.from_user.id, cart)
    await message.answer(nt(lang,"added_to_cart", name=product["name"]))
    # Adminga xabar
    await notify_admin_order(message.from_user, product, cat)

# --- Yetkazib berish bog'lanish ---
@dp.message(UserState.in_delivery, F.text.in_(all_contact_texts()))
async def delivery_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    await message.answer(t(lang,"contact_link_text"), reply_markup=get_contact_inline_keyboard(lang))
    await notify_admin_delivery_request(message.from_user)
# ===========================================================================
# 7) ADMIN HANDLERLARI
# ===========================================================================

@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz!"); return
    await state.set_state(AdminState.menu)
    await message.answer("🛠 Admin panel:", reply_markup=admin_menu_keyboard())

# Chiqish
@dp.message(AdminState.menu, F.text == "🚪 Admin rejimidan chiqish")
async def admin_exit(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","uz")
    await state.set_state(UserState.in_main_menu)
    await message.answer("Admin rejimidan chiqdingiz.", reply_markup=get_categories_keyboard(lang, message.from_user.id))

# Ro'yxat
@dp.message(AdminState.menu, F.text == "📋 Mahsulotlar ro'yxati")
async def admin_list(message: Message, state: FSMContext):
    products = get_products()
    lines = []
    for ck, cl in CATEGORY_LABELS_UZ.items():
        items = products.get(ck,[])
        lines.append(f"\n{cl} ({len(items)} ta):")
        if not items: lines.append("  — bo'sh —")
        for p in items:
            qty_txt = f" | Qoldi: {p['qty']}" if p.get("qty") is not None else ""
            sold    = p.get("sold",0)
            photos_count = len(get_product_photos(p))
            lines.append(f"  • {p['name']} — {p['price']}{qty_txt} | Sotildi: {sold} | 📸{photos_count}")
    await message.answer("\n".join(lines) or "Mahsulotlar yo'q.")

# Statistika
@dp.message(AdminState.menu, F.text == "📊 Statistika")
async def admin_stats(message: Message, state: FSMContext):
    text = build_stats_text()
    await message.answer(text)

def build_stats_text(period_days=None):
    orders   = load_orders()
    users    = load_users()
    products = get_products()
    if period_days:
        cutoff = datetime.now() - timedelta(days=period_days)
        orders_in_period = [o for o in orders if _parse_order_date(o["date"]) >= cutoff]
    else:
        orders_in_period = orders
    total_orders = len(orders_in_period)
    total_users  = len(users)
    sold_list = []
    for cat_items in products.values():
        for p in cat_items:
            if p.get("sold",0) > 0:
                sold_list.append((p["name"], p.get("sold",0)))
    sold_list.sort(key=lambda x: x[1], reverse=True)
    top = "\n".join(f"  {i+1}. {n} — {s} ta" for i,(n,s) in enumerate(sold_list[:5])) or "  —"
    new_cnt  = sum(1 for o in orders_in_period if o["status"]=="new")
    acc_cnt  = sum(1 for o in orders_in_period if o["status"]=="accepted")
    del_cnt  = sum(1 for o in orders_in_period if o["status"]=="delivered")
    can_cnt  = sum(1 for o in orders_in_period if o["status"]=="cancelled")
    period_label = f"(so'nggi {period_days} kun)" if period_days else "(umumiy)"
    return (
        f"📊 Statistika {period_label}\n\n"
        f"👥 Foydalanuvchilar: {total_users}\n"
        f"📦 Buyurtmalar: {total_orders}\n"
        f"  🆕 Yangi: {new_cnt}\n"
        f"  ✅ Qabul qilingan: {acc_cnt}\n"
        f"  🚚 Yetkazilgan: {del_cnt}\n"
        f"  ❌ Bekor qilingan: {can_cnt}\n\n"
        f"🏆 Ko'p sotilgan:\n{top}"
    )

def _parse_order_date(date_str):
    try:
        return datetime.strptime(date_str, "%d.%m.%Y %H:%M")
    except Exception:
        return datetime.min
# Buyurtmalarni boshqarish
@dp.message(AdminState.menu, F.text == "📦 Buyurtmalar")
async def admin_orders(message: Message, state: FSMContext):
    orders = load_orders()
    if not orders:
        await message.answer("Buyurtmalar yo'q."); return
    for o in orders[-10:]:
        items_str = ", ".join(i["name"] for i in o["items"])
        delivery_str = f"\n🚚 Yetkazib berish: {o.get('delivery_fee',0)} {DELIVERY_CURRENCY}" if o.get('delivery_fee',0) > 0 else ""
        text = (f"#{o['id']} | {o['date']}\n"
                f"Xaridor: {o['user_name']} (@{o['username']})\n"
                f"Mahsulotlar: {items_str}\n"
                f"Chegirma: {o.get('discount',0)}%{delivery_str}\n"
                f"Holat: {o['status']}")
        await message.answer(text, reply_markup=order_status_inline(o["id"]))

@dp.callback_query(F.data.startswith("ostatus_"))
async def change_order_status(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    _, oid, new_status = cb.data.split("_", 2)
    orders = load_orders()
    for o in orders:
        if o["id"] == oid:
            o["status"] = new_status
            try:
                buyer_lang = get_user(o["user_id"]).get("lang", "uz")
                msgs = {
                    "accepted": {
                        "uz": f"✅ Buyurtma #{oid} qabul qilindi!\n🕐 Tez orada yetkazib beramiz.",
                        "ru": f"✅ Заказ #{oid} принят!\n🕐 Скоро доставим.",
                        "en": f"✅ Order #{oid} accepted!\n🕐 We'll deliver soon.",
                    },
                    "delivered": {
                        "uz": f"🎉 Buyurtma #{oid} yetkazildi!\nRahmat! Yana buyurtma bering 😊",
                        "ru": f"🎉 Заказ #{oid} доставлен!\nСпасибо! Заходите снова 😊",
                        "en": f"🎉 Order #{oid} delivered!\nThank you! Come again 😊",
                    },
                    "cancelled": {
                        "uz": f"❌ Buyurtma #{oid} bekor qilindi.\nSabab bo'yicha admin bilan bog'laning.",
                        "ru": f"❌ Заказ #{oid} отменён.\nСвяжитесь с администратором.",
                        "en": f"❌ Order #{oid} cancelled.\nContact admin for details.",
                    },
                }
                text = msgs.get(new_status, {}).get(buyer_lang, msgs.get(new_status, {}).get("uz", ""))
                if text:
                    contact_kb = get_contact_inline_keyboard(buyer_lang)
                    await bot.send_message(int(o["user_id"]), text,
                        reply_markup=contact_kb if new_status == "cancelled" else None)
            except Exception as e:
                logger.error(e)
            break
    save_orders(orders)
    await cb.answer(f"✅ Holat: {new_status}")
    await cb.message.edit_reply_markup(reply_markup=None)

# Admin #N kod yozsa — ISTALGAN holatda buyurtmani topib ko'rsatadi
@dp.message(F.text.regexp(r'^#\d+$'))
async def admin_order_by_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    oid = message.text[1:]
    order = get_order_by_id(oid)
    if not order:
        await message.answer(f"❌ #{oid} buyurtma topilmadi."); return
    items_str = ", ".join(i["name"] for i in order["items"])
    delivery_str = f"\n🚚 Yetkazib berish: {order.get('delivery_fee',0)} {DELIVERY_CURRENCY}" if order.get('delivery_fee',0) > 0 else ""
    text = (f"📦 Buyurtma #{oid}\n"
            f"👤 {order['user_name']} (@{order.get('username','—')})\n"
            f"📩 Lichka: tg://user?id={order['user_id']}\n"
            f"🛒 {items_str}{delivery_str}\n"
            f"📅 {order['date']}\n"
            f"🔖 Holat: {order['status']}")
    await message.answer(text, reply_markup=order_status_inline(oid))

# Chegirmalarni boshqarish
@dp.message(AdminState.menu, F.text == "💰 Chegirmalarni boshqarish")
async def admin_manage_discounts(message: Message, state: FSMContext):
    promos = load_promos()
    if not promos:
        await message.answer("Hozircha promo-kodlar yo'q.\n\n🎟 Promo-kod qo'shish orqali yangi чегирма yarating.",
                             reply_markup=admin_menu_keyboard()); return
    lines = ["📋 Faol promo-kodlar:\n"]
    for code, info in promos.items():
        kind = "🎁 Referal" if info.get("referral") else ("🏆 Sodiqlik" if info.get("loyalty") else "🎟 Oddiy")
        lines.append(f"• <code>{code}</code> — {info['discount']}% {kind}")
    lines.append("\n❌ O'chirish uchun kodni yuboring yoki /skip yozing.")
    await state.set_state(AdminState.manage_discount)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.manage_discount)
async def admin_delete_promo(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.set_state(AdminState.menu)
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard()); return
    code = message.text.strip().upper()
    promos = load_promos()
    if code in promos:
        del promos[code]
        save_promos(promos)
        await message.answer(f"✅ <code>{code}</code> o'chirildi.", parse_mode="HTML")
    else:
        await message.answer(f"❌ <code>{code}</code> topilmadi.", parse_mode="HTML")
    await state.set_state(AdminState.menu)
    await message.answer("Admin panel:", reply_markup=admin_menu_keyboard())

# Ommaviy xabar
@dp.message(AdminState.menu, F.text == "📢 Ommaviy xabar")
async def admin_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.broadcast_text)
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni yozing:", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.broadcast_text)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.set_state(AdminState.menu); await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard()); return
    users = load_users()
    count = 0
    for uid in users:
        try:
            await bot.send_message(int(uid), message.text)
            count += 1
        except: pass
    await state.set_state(AdminState.menu)
    await message.answer(nt("uz","broadcast_sent",count=count), reply_markup=admin_menu_keyboard())

# Promo-kod qo'shish
@dp.message(AdminState.menu, F.text == "🎟 Promo-kod qo'shish")
async def admin_add_promo_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.add_promo_code)
    await message.answer("Yangi promo-kod kiriting (masalan: SALE20):", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.add_promo_code)
async def admin_add_promo_code(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.set_state(AdminState.menu); await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard()); return
    await state.update_data(promo_code=message.text.upper())
    await state.set_state(AdminState.add_promo_discount)
    await message.answer("Chegirma foizini kiriting (masalan: 10):")

@dp.message(AdminState.add_promo_discount)
async def admin_add_promo_discount(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        disc = int(message.text)
        promos = load_promos()
        promos[data["promo_code"]] = {"discount": disc}
        save_promos(promos)
        await state.set_state(AdminState.menu)
        await message.answer(f"✅ Promo-kod qo'shildi: {data['promo_code']} — {disc}%", reply_markup=admin_menu_keyboard())
    except:
        await message.answer("Raqam kiriting.")

# --- Eksport (CSV) ---
@dp.message(AdminState.menu, F.text == "📤 Eksport (CSV)")
async def admin_export_csv(message: Message, state: FSMContext):
    orders = load_orders()
    if not orders:
        await message.answer("Buyurtmalar yo'q, eksport qilish uchun hech narsa topilmadi."); return

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Sana", "Xaridor", "Username", "User ID", "Mahsulotlar", "Chegirma %", "Yetkazib berish", "Holat"])
    for o in orders:
        items_str = "; ".join(f"{i['name']} ({i['price']})" for i in o["items"])
        writer.writerow([o["id"], o["date"], o["user_name"], o.get("username",""), o["user_id"], items_str, o.get("discount",0), o.get("delivery_fee",0), o["status"]])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM — Excelda kirill harflari to'g'ri ochilishi uchun
    filename = f"orders_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    file = BufferedInputFile(csv_bytes, filename=filename)
    await message.answer_document(file, caption=f"📤 {len(orders)} ta buyurtma eksport qilindi.")

# --- Top mijozlar ---
@dp.message(AdminState.menu, F.text == "👥 Top mijozlar")
async def admin_top_customers(message: Message, state: FSMContext):
    orders = load_orders()
    if not orders:
        await message.answer("Buyurtmalar yo'q."); return

    stats = {}
    for o in orders:
        uid = o["user_id"]
        if uid not in stats:
            stats[uid] = {"name": o["user_name"], "username": o.get("username",""), "orders": 0, "items": {}}
        stats[uid]["orders"] += 1
        for item in o["items"]:
            stats[uid]["items"][item["name"]] = stats[uid]["items"].get(item["name"], 0) + 1

    ranked = sorted(stats.items(), key=lambda kv: kv[1]["orders"], reverse=True)
    lines = ["👥 Top mijozlar (buyurtmalar soni bo'yicha):\n"]
    for i, (uid, info) in enumerate(ranked[:15], 1):
        top_item = max(info["items"].items(), key=lambda kv: kv[1])[0] if info["items"] else "—"
        lines.append(f"{i}. {info['name']} (@{info['username'] or '—'}) — {info['orders']} buyurtma | Sevimli: {top_item}")
    await message.answer("\n".join(lines))
# Mahsulot qo'shish
@dp.message(AdminState.menu, F.text == "➕ Mahsulot qo'shish")
async def admin_add_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.add_choosing_category)
    await message.answer("Qaysi bo'limga?", reply_markup=admin_category_keyboard())

@dp.message(AdminState.add_choosing_category, F.text == "❌ Bekor qilish")
@dp.message(AdminState.add_name, F.text == "❌ Bekor qilish")
@dp.message(AdminState.add_price, F.text == "❌ Bekor qilish")
@dp.message(AdminState.add_qty, F.text == "❌ Bekor qilish")
@dp.message(AdminState.add_photo, F.text == "❌ Bekor qilish")
@dp.message(AdminState.add_description, F.text == "❌ Bekor qilish")
async def admin_cancel_add(message: Message, state: FSMContext):
    await state.set_state(AdminState.menu)
    await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())

@dp.message(AdminState.add_choosing_category)
async def admin_add_category(message: Message, state: FSMContext):
    cat = find_category_key_by_uz_label(message.text)
    if not cat:
        await message.answer("Bo'limni ro'yxatdan tanlang.", reply_markup=admin_category_keyboard()); return
    await state.update_data(new_category=cat)
    await state.set_state(AdminState.add_name)
    await message.answer("Mahsulot nomini kiriting:", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.add_name)
async def admin_add_name(message: Message, state: FSMContext):
    await state.update_data(new_name=message.text)
    await state.set_state(AdminState.add_price)
    await message.answer("Narxini kiriting (masalan: 150 000 so'm):", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.add_price)
async def admin_add_price(message: Message, state: FSMContext):
    await state.update_data(new_price=message.text)
    await state.set_state(AdminState.add_qty)
    await message.answer("Mahsulot sonini kiriting (soni cheksiz bo'lsa: 0 yozing):", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.add_qty)
async def admin_add_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text)
        await state.update_data(new_qty=None if qty == 0 else qty)
    except:
        await state.update_data(new_qty=None)
    await state.update_data(new_photos=[])
    await state.set_state(AdminState.add_photo)
    await message.answer(
        "Mahsulot rasm(lar)ini yuboring (1 yoki bir nechta, ketma-ket).\n"
        "Hammasini yuborib bo'lgach, \"✅ Rasmlar tayyor\" tugmasini bosing.",
        reply_markup=admin_photo_done_keyboard()
    )

@dp.message(AdminState.add_photo, F.photo)
async def admin_add_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("new_photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(new_photos=photos)
    await message.answer(f"✅ Qabul qilindi ({len(photos)} ta rasm). Yana rasm yuborishingiz mumkin yoki \"✅ Rasmlar tayyor\"ni bosing.")

@dp.message(AdminState.add_photo, F.text == "✅ Rasmlar tayyor")
async def admin_add_photo_done(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("new_photos", [])
    if not photos:
        await message.answer("Kamida 1 ta rasm yuboring."); return
    await state.set_state(AdminState.add_description)
    await message.answer("Tavsif yozing:", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.add_photo)
async def admin_add_photo_wrong(message: Message, state: FSMContext):
    await message.answer("Iltimos, rasm yuboring yoki \"✅ Rasmlar tayyor\"ni bosing.")

@dp.message(AdminState.add_description)
async def admin_add_description(message: Message, state: FSMContext):
    data = await state.get_data()
    product = add_product(
        data["new_category"], data["new_name"], data["new_price"],
        data["new_photos"], message.text, data.get("new_qty")
    )
    await state.set_state(AdminState.menu)
    await message.answer(
        f"✅ Qo'shildi!\nNomi: {data['new_name']}\nNarx: {data['new_price']}\n"
        f"Soni: {data.get('new_qty') or 'cheksiz'}\n📸 Rasmlar: {len(data['new_photos'])} ta",
        reply_markup=admin_menu_keyboard()
    )
    await notify_subscribers_new_product(product)
# Mahsulot o'chirish
@dp.message(AdminState.menu, F.text == "🗑 Mahsulotni o'chirish")
async def admin_delete_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.delete_choosing)
    await message.answer("O'chirish uchun bo'limni tanlang:", reply_markup=admin_category_keyboard())

@dp.message(AdminState.delete_choosing, F.text == "❌ Bekor qilish")
async def admin_delete_cancel(message: Message, state: FSMContext):
    await state.set_state(AdminState.menu)
    await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())

@dp.message(AdminState.delete_choosing)
async def admin_delete_choose(message: Message, state: FSMContext):
    cat = find_category_key_by_uz_label(message.text)
    if not cat:
        await message.answer("Bo'limni tanlang.", reply_markup=admin_category_keyboard()); return
    products = get_products()
    items    = products.get(cat, [])
    if not items:
        await message.answer("Bu bo'limda mahsulot yo'q."); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p["name"], callback_data=f"del_{p['id']}")] for p in items
    ])
    await state.set_state(AdminState.menu)
    await message.answer("O'chiriladigan mahsulotni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("del_"))
async def admin_delete_product(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    pid      = cb.data[4:]
    products = load_products()
    deleted  = False
    for cat_items in products.values():
        for p in cat_items:
            if p["id"] == pid:
                cat_items.remove(p)
                deleted = True
                break
        if deleted: break
    if deleted:
        save_products(products)
        await cb.answer("✅ Mahsulot o'chirildi.")
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.message.answer("✅ O'chirildi.", reply_markup=admin_menu_keyboard())
    else:
        await cb.answer("Topilmadi.")

# Mahsulot tahrirlash
@dp.message(AdminState.menu, F.text == "✏️ Mahsulotni tahrirlash")
async def admin_edit_start(message: Message, state: FSMContext):
    products = get_products()
    buttons  = []
    for cat, items in products.items():
        for p in items:
            buttons.append([InlineKeyboardButton(text=f"[{CATEGORY_LABELS_UZ.get(cat,cat)}] {p['name']}", callback_data=f"edit_{p['id']}")])
    if not buttons:
        await message.answer("Mahsulotlar yo'q."); return
    await message.answer("Tahrirlanadigan mahsulotni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("edit_"))
async def admin_edit_choose_field(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    pid = cb.data[5:]
    await state.update_data(edit_pid=pid)
    await state.set_state(AdminState.edit_field)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Nomi",   callback_data="efield_name")],
        [InlineKeyboardButton(text="💰 Narxi",  callback_data="efield_price")],
        [InlineKeyboardButton(text="📦 Soni",   callback_data="efield_qty")],
        [InlineKeyboardButton(text="📄 Tavsif", callback_data="efield_description")],
        [InlineKeyboardButton(text="📸 Rasmlar (qayta yuklash)", callback_data="efield_photos")],
    ])
    await cb.message.answer("Qaysi maydonni tahrirlamoqchisiz?", reply_markup=kb)
    await cb.answer()

@dp.callback_query(AdminState.edit_field, F.data.startswith("efield_"))
async def admin_edit_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data[7:]
    await state.update_data(edit_field=field, edit_photos_buffer=[])
    await state.set_state(AdminState.edit_value)
    if field == "photos":
        await cb.message.answer(
            "Yangi rasm(lar)ni yuboring. Hammasi yuborilgach \"✅ Rasmlar tayyor\"ni bosing — "
            "eski rasmlar o'rniga shu rasmlar saqlanadi.",
            reply_markup=admin_photo_done_keyboard()
        )
    else:
        await cb.message.answer(f"Yangi qiymatni kiriting ({field}):", reply_markup=admin_cancel_keyboard())
    await cb.answer()

@dp.message(AdminState.edit_value, F.photo)
async def admin_edit_value_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "photos":
        return  # rasm kutilmayotgan bo'lsa e'tiborsiz qoldiramiz
    buf = data.get("edit_photos_buffer", [])
    buf.append(message.photo[-1].file_id)
    await state.update_data(edit_photos_buffer=buf)
    await message.answer(f"✅ Qabul qilindi ({len(buf)} ta). Yana yuborishingiz mumkin yoki \"✅ Rasmlar tayyor\"ni bosing.")

@dp.message(AdminState.edit_value, F.text == "✅ Rasmlar tayyor")
async def admin_edit_value_photos_done(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "photos":
        await state.set_state(AdminState.menu); return
    buf = data.get("edit_photos_buffer", [])
    if not buf:
        await message.answer("Kamida 1 ta rasm yuboring."); return
    pid = data.get("edit_pid")
    products = load_products()
    updated = False
    for cat_items in products.values():
        for p in cat_items:
            if p["id"] == pid:
                p["photos"] = buf
                p.pop("photo", None)
                updated = True
                break
        if updated: break
    if updated:
        save_products(products)
        await message.answer(f"✅ Rasmlar yangilandi ({len(buf)} ta).", reply_markup=admin_menu_keyboard())
    else:
        await message.answer("Mahsulot topilmadi.", reply_markup=admin_menu_keyboard())
    await state.set_state(AdminState.menu)

@dp.message(AdminState.edit_value)
async def admin_edit_value(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.set_state(AdminState.menu); await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard()); return
    data     = await state.get_data()
    field    = data.get("edit_field")
    if field == "photos":
        await message.answer("Iltimos, rasm yuboring yoki \"✅ Rasmlar tayyor\"ni bosing.")
        return
    pid      = data.get("edit_pid")
    products = load_products()
    updated  = False
    for cat_items in products.values():
        for p in cat_items:
            if p["id"] == pid:
                if field == "qty":
                    try: p["qty"] = None if int(message.text)==0 else int(message.text)
                    except: pass
                else:
                    p[field] = message.text
                updated = True
                break
        if updated: break
    if updated:
        save_products(products)
        await message.answer(f"✅ {field} yangilandi.", reply_markup=admin_menu_keyboard())
    else:
        await message.answer("Mahsulot topilmadi.", reply_markup=admin_menu_keyboard())
    await state.set_state(AdminState.menu)
# --- Izohlarni moderatsiya qilish ---
@dp.message(AdminState.menu, F.text == "💬 Izohlarni moderatsiya")
async def admin_moderate_comments(message: Message, state: FSMContext):
    pending = get_pending_comments()
    if not pending:
        await message.answer("Tasdiqlanmagan izohlar yo'q. 👌"); return
    for c in pending[:10]:
        product = find_product_by_id(c["product_id"])
        pname = product["name"] if product else c["product_id"]
        text = (f"💬 Изоҳ #{c['id']}\n"
                f"Маҳсулот: {pname}\n"
                f"Фойдаланувчи: {c['user_name']}\n"
                f"Матн: {c['text']}\n"
                f"Сана: {c['date']}")
        await message.answer(text, reply_markup=comment_moderation_inline(c["id"]))

@dp.callback_query(F.data.startswith("cmtok_"))
async def comment_approve(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    cid = cb.data[6:]
    c = set_comment_status(cid, "approved")
    await cb.answer("✅ Tasdiqlandi")
    await cb.message.edit_reply_markup(reply_markup=None)
    if c:
        try:
            lang = get_user(c["user_id"]).get("lang", "uz")
            await bot.send_message(int(c["user_id"]), nt(lang, "comment_approved_notice"))
        except Exception as e:
            logger.error(e)

@dp.callback_query(F.data.startswith("cmtno_"))
async def comment_reject(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    cid = cb.data[6:]
    c = set_comment_status(cid, "rejected")
    await cb.answer("❌ Rad etildi")
    await cb.message.edit_reply_markup(reply_markup=None)
    if c:
        try:
            lang = get_user(c["user_id"]).get("lang", "uz")
            await bot.send_message(int(c["user_id"]), nt(lang, "comment_rejected_notice"))
        except Exception as e:
            logger.error(e)

# --- FAQ boshqarish ---
def admin_faq_menu_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Savol qo'shish"), KeyboardButton(text="📋 FAQ ro'yxati")],
        [KeyboardButton(text="🗑 Savolni o'chirish")],
        [KeyboardButton(text="⬅️ Admin menyuga qaytish")],
    ], resize_keyboard=True)

@dp.message(AdminState.menu, F.text == "❓ FAQ boshqarish")
async def admin_faq_menu(message: Message, state: FSMContext):
    await message.answer("❓ FAQ boshqarish:", reply_markup=admin_faq_menu_keyboard())

@dp.message(AdminState.menu, F.text == "⬅️ Admin menyuga qaytish")
async def admin_faq_back(message: Message, state: FSMContext):
    await message.answer("🛠 Admin panel:", reply_markup=admin_menu_keyboard())

@dp.message(AdminState.menu, F.text == "📋 FAQ ro'yxati")
async def admin_faq_list(message: Message, state: FSMContext):
    faqs = load_faq()
    if not faqs:
        await message.answer("FAQ bo'sh."); return
    lines = [f"#{f['id']} {f['question']}\n   ↳ {f['answer']}" for f in faqs]
    await message.answer("\n\n".join(lines))

@dp.message(AdminState.menu, F.text == "➕ Savol qo'shish")
async def admin_faq_add_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.add_faq_question)
    await message.answer("Savolni kiriting:", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.add_faq_question, F.text == "❌ Bekor qilish")
@dp.message(AdminState.add_faq_answer, F.text == "❌ Bekor qilish")
async def admin_faq_add_cancel(message: Message, state: FSMContext):
    await state.set_state(AdminState.menu)
    await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())

@dp.message(AdminState.add_faq_question)
async def admin_faq_add_question(message: Message, state: FSMContext):
    await state.update_data(faq_question=message.text)
    await state.set_state(AdminState.add_faq_answer)
    await message.answer("Javobni kiriting:", reply_markup=admin_cancel_keyboard())

@dp.message(AdminState.add_faq_answer)
async def admin_faq_add_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    add_faq(data["faq_question"], message.text)
    await state.set_state(AdminState.menu)
    await message.answer("✅ Savol qo'shildi.", reply_markup=admin_menu_keyboard())

@dp.message(AdminState.menu, F.text == "🗑 Savolni o'chirish")
async def admin_faq_delete_start(message: Message, state: FSMContext):
    faqs = load_faq()
    if not faqs:
        await message.answer("FAQ bo'sh."); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f["question"][:40], callback_data=f"faqdel_{f['id']}")] for f in faqs
    ])
    await message.answer("O'chiriladigan savolni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("faqdel_"))
async def admin_faq_delete_confirm(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    fid = cb.data[7:]
    delete_faq(fid)
    await cb.answer("✅ O'chirildi")
    await cb.message.edit_reply_markup(reply_markup=None)
# ===========================================================================
# 8) ADMIN XABAR FUNKSIYALARI
# ===========================================================================

async def _send_to_all_admins(text, reply_markup=None):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(e)

async def notify_admin_order(user, product, category):
    if not ADMIN_IDS: return
    text = (f"🆕 Саватчага qo'shildi!\n\n"
            f"Mahsulot: {product['name']}\nNarx: {product['price']}\n"
            f"Kategoriya: {category}\n\n"
            f"Foydalanuvchi: {user.full_name} (@{user.username or '—'})\n"
            f"User ID: {user.id}\ntg://user?id={user.id}")
    await _send_to_all_admins(text)

async def notify_admin_cart_order(user, cart, order_id, discount=0, delivery_fee=0, user_lat=None, user_lon=None):
    if not ADMIN_IDS: return
    items_str = "\n".join(f"  • {i['name']} — {i['price']}" for i in cart)
    delivery_str = f"\n🚚 Yetkazib berish: {delivery_fee:.0f} {DELIVERY_CURRENCY}" if delivery_fee > 0 else ""
    text = (f"🔔 YANGI BUYURTМА #{order_id} | Kod: #{order_id}!\n\n"
            f"Mahsulotlar:\n{items_str}\n"
            f"Chegirma: {discount}%{delivery_str}\n\n"
            f"Xaridor: {user.full_name} (@{user.username or '—'})\n"
            f"📩 Lichka: tg://user?id={user.id}")
    # Tovushli xabarnoma + xarita
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(int(admin_id), "🔔🔔🔔 ЯНГИ ЗАКАЗ ТУШДИ!")
            await bot.send_message(int(admin_id), text, reply_markup=order_status_inline(order_id))
            # Xaridor lokatsiyasini xarita sifatida yuborish
            if user_lat and user_lon:
                await bot.send_location(int(admin_id), latitude=user_lat, longitude=user_lon)
        except Exception as e:
            logger.error(f"Admin xabarnoma xatosi: {e}")

async def notify_admin_delivery_request(user):
    if not ADMIN_IDS: return
    text = (f"🚚 Yetkazib berish so'rovi!\n\n"
            f"Foydalanuvchi: {user.full_name} (@{user.username or '—'})\n"
            f"ID: {user.id}\ntg://user?id={user.id}")
    await _send_to_all_admins(text)

async def notify_admin_new_comment(user, product_id, comment_id, text_body):
    if not ADMIN_IDS: return
    product = find_product_by_id(product_id)
    pname = product["name"] if product else product_id
    text = (f"💬 Yangi izoh (#{comment_id})!\n\n"
            f"Маҳсулот: {pname}\n"
            f"Foydalanuvchi: {user.full_name} (@{user.username or '—'})\n"
            f"Matn: {text_body}\n\n"
            f"Tasdiqlash uchun: 🛠 Admin panel → 💬 Izohlarni moderatsiya")
    await _send_to_all_admins(text, reply_markup=comment_moderation_inline(comment_id))

async def notify_admin_low_stock(product):
    if not ADMIN_IDS: return
    text = f"⚠️ \"{product['name']}\" mahsulotidan faqat {product['qty']} dona qoldi! Vaqtida to'ldirib qo'ying."
    await _send_to_all_admins(text)

async def notify_subscribers_new_product(product):
    """Barcha 'subscribed_new_products' bo'lgan foydalanuvchilarga yangi mahsulot haqida xabar."""
    users = load_users()
    photos = get_product_photos(product)
    for uid, u in users.items():
        if not u.get("subscribed_new_products", True):
            continue
        lang = u.get("lang", "uz")
        text = nt(lang, "new_product_notice", name=product["name"], price=product["price"], description=product["description"])
        try:
            if photos:
                await bot.send_photo(int(uid), photo=photos[0], caption=text, parse_mode="HTML")
            else:
                await bot.send_message(int(uid), text, parse_mode="HTML")
        except Exception:
            pass
# ===========================================================================
# 9) AVTOMATLASHTIRISH (BACKGROUND TASKLAR)
# ===========================================================================
#
# MUHIM ESLATMA: quyidagi background tasklar foydalanuvchi savatchasini FSM
# xotirasidan (MemoryStorage) emas, balki users.json dagi vaqt belgisidan
# (cart_last_updated) aniqlaydi. Shu sababli savatcha tarkibini eslatmada
# ko'rsatish uchun oxirgi "savatchaga qo'shilgan" mahsulot nomini ham users.json
# ichida saqlab boramiz (cart_last_items).
#
# Bu funksiya ishlashi uchun process_buy() va boshqa joylarda touch_user_cart()
# chaqirilganda mahsulot ro'yxati ham saqlanadi (pastdagi yordamchi orqali).

def touch_user_cart_items(user_id, cart_items):
    """Саватчадаgi joriy mahsulotlar nomini users.json ga yozib qo'yadi (eslatma matni uchun)."""
    users = load_users()
    uid = str(user_id)
    if uid not in users: return
    users[uid]["cart_last_items"] = [i["name"] for i in cart_items]
    save_users(users)

async def cart_reminder_loop():
    """Har 30 daqiqada savatchasi to'lib, CART_REMINDER_HOURS soatdan beri
    buyurtma bermagan foydalanuvchilarga eslatma yuboradi."""
    while True:
        try:
            users = load_users()
            now = datetime.now()
            for uid, u in users.items():
                last_updated = u.get("cart_last_updated")
                if not last_updated or u.get("cart_reminder_sent"):
                    continue
                try:
                    last_dt = datetime.fromisoformat(last_updated)
                except Exception:
                    continue
                if now - last_dt >= timedelta(hours=CART_REMINDER_HOURS):
                    lang = u.get("lang", "uz")
                    items = u.get("cart_last_items", [])
                    items_text = "\n".join(f"  • {n}" for n in items) if items else "—"
                    try:
                        await bot.send_message(int(uid), nt(lang, "cart_reminder", items=items_text))
                        mark_cart_reminder_sent(uid)
                    except Exception as e:
                        logger.error(f"Cart reminder error for {uid}: {e}")
        except Exception as e:
            logger.error(f"cart_reminder_loop error: {e}")
        await asyncio.sleep(30 * 60)  # 30 daqiqa

async def daily_report_loop():
    """Har kuni belgilangan soatda (DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE)
    barcha adminlarga avtomatik statistika hisobotini yuboradi."""
    while True:
        try:
            now = datetime.now()
            target = now.replace(hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            text = "📈 Kunlik avtomatik hisobot\n\n" + build_stats_text(period_days=1)
            await _send_to_all_admins(text)
        except Exception as e:
            logger.error(f"daily_report_loop error: {e}")
            await asyncio.sleep(60)

async def weekly_report_loop():
    """Har dushanba kuni DAILY_REPORT_HOUR da haftalik hisobot yuboradi."""
    while True:
        try:
            now = datetime.now()
            days_ahead = (7 - now.weekday()) % 7  # 0 = dushanba
            if days_ahead == 0:
                target = now.replace(hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, second=0, microsecond=0)
                if target <= now:
                    days_ahead = 7
            target = (now + timedelta(days=days_ahead)).replace(
                hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, second=0, microsecond=0
            )
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(max(wait_seconds, 60))
            text = "📈 Haftalik avtomatik hisobot\n\n" + build_stats_text(period_days=7)
            await _send_to_all_admins(text)
        except Exception as e:
            logger.error(f"weekly_report_loop error: {e}")
            await asyncio.sleep(60)
# ===========================================================================
# 10) ISHGA TUSHIRISH
# ===========================================================================
async def main():
    logger.info("Bot ishga tushmoqda...")

    if not _SETTINGS_OK:
        # Sabab yuqorida (_sanity_check_settings ichida) allaqachon chop etilgan.
        raise SystemExit(1)

    # Telegram bilan birinchi aloqa — token va internetni shu yerda tekshiramiz.
    try:
        me = await bot.get_me()
        logger.info(f"✅ Botga ulanish muvaffaqiyatli: @{me.username}")
    except Exception as e:
        err_text = str(e)
        print("\n" + "="*70)
        print("❌ BOTGA TELEGRAM ORQALI ULANIB BO'LMADI!")
        print("="*70)
        if "Unauthorized" in err_text or "401" in err_text:
            print(
                "\nSabab: TOKEN NOTO'G'RI.\n"
                "  → Fayl boshidagi BOT_TOKEN qatoriga @BotFather bergan tokenni\n"
                "    qaytadan, to'liq va xatosiz nusxalab qo'ying.\n"
                "  → Eski/bekor qilingan tokenlar ham shu xatoni beradi — agar\n"
                "    tokenni @BotFather'da /revoke qilgan bo'lsangiz, yangisini oling."
            )
        elif any(k in err_text for k in ["Network", "Connection", "Timeout", "resolve", "getaddrinfo"]):
            print(
                "\nSabab: INTERNET ULANISHI YO'Q yoki Telegram serveriga\n"
                "  yetib bo'lmayapti.\n"
                "  → Wi-Fi/mobil internetni tekshiring.\n"
                "  → Agar mamlakatingizda Telegram bloklangan bo'lsa, VPN yoqing."
            )
        else:
            print(f"\nXato matni: {err_text}")
            print(
                "\n  → Yuqoridagi xato matnini diqqat bilan o'qing yoki shu matnni\n"
                "    nusxalab, yordam so'rang."
            )
        print("="*70 + "\n")
        raise SystemExit(1)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"delete_webhook chaqirishda kichik xato (e'tiborsiz qoldirilishi mumkin): {e}")

    # Background tasklarni ishga tushiramiz (savatcha eslatmasi, kunlik/haftalik hisobot)
    asyncio.create_task(cart_reminder_loop())
    asyncio.create_task(daily_report_loop())
    asyncio.create_task(weekly_report_loop())

    logger.info("🚀 Bot ishga tushdi va xabarlarni qabul qilishga tayyor (polling boshlandi)...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print("\n" + "="*70)
        print("❌ BOT POLLING DAVOMIDA TO'XTADI!")
        print("="*70)
        print(f"\nXato matni: {e}")
        print("="*70 + "\n")
        raise

if __name__ == "__main__":
    _had_error = False
    try:
        asyncio.run(main())
    except SystemExit:
        _had_error = True
    except 5:
        print("\nBot to'xtatildi (foydalanuvchi tomonidan).")
    except Exception as e:
        _had_error = True
        print("\n" + "="*70)
        print("❌ KUTILMAGAN XATO YUZ BERDI:")
        print("="*70)
        print(f"\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print("="*70 + "\n")
    if _had_error:
        try:
            input("\n⬆️ Yuqoridagi xato matnini o'qing. Chiqish uchun Enter bosing...")
        except Exception:
            pass
