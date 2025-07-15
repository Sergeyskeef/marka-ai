# stub: точка входа Telegram-бота
import asyncio


async def main():
    print("Telegram bot stub running")
    # Заглушка для предотвращения завершения
    while True:
        await asyncio.sleep(3600)  # Спим час


if __name__ == "__main__":
    asyncio.run(main()) 