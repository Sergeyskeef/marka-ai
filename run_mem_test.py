import asyncio, sys, os, traceback
sys.path.append('/srv/mark/langchain_api')
os.environ['MARK_MEMORY_FACADE']='1'

async def main():
    try:
        from core.memory.memory_manager import memory_manager
        print('imported memory_manager')
        r = await memory_manager.add_episode('MARK TEST: память фасада с эмбеддингом', {'user_id':'dev'})
        print('store:', r)
        res = await memory_manager.hybrid_search(query='память фасада', user_id='dev', k=3)
        print('search:', res)
    except Exception as e:
        with open('/tmp/trace.txt','w') as f:
            traceback.print_exc(file=f)
        print('ERR:', e)

asyncio.run(main())
