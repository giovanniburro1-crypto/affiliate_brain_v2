"""
Создание нового campaign_analysis_service.py с интеграцией MY_KNOWLEDGE
"""

NEW_CODE = open('logic_blocks/my_knowledge/block_1_base.py').read()

print("✅ Файл block_1_base.py прочитан")
print(f"Размер: {len(NEW_CODE)} символов")

# Теперь создаем новый сервис
import shutil

# Бэкап старого
shutil.copy('backend/services/campaign_analysis_service.py', 
            'backend/services/campaign_analysis_service.py.backup')

print("✅ Бэкап создан: campaign_analysis_service.py.backup")
print("\nТеперь создаю новый файл...")
