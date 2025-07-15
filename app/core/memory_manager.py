import uuid


class MemoryManager:
    def create_snapshot(self, session_id, object_types, with_state=False, meta=None):
        """Создает снапшот для указанных типов объектов"""
        try:
            # Генерируем уникальный ID для снапшота
            snapshot_id = str(uuid.uuid4())

            # Получаем текущее состояние объектов
            object_states = None
            if with_state:
                # Получаем только объекты для текущей сессии
                states = {}
                for obj_type in object_types:
                    collection = self.memory_registry.get(obj_type)
                    if collection:
                        # Получаем только объекты для текущей сессии
                        objects = collection.query_by_filter({
                            "path": ["session_id"],
                            "operator": "Equal",
                            "valueString": session_id
                        })
                        if objects:
                            # Сохраняем только необходимые поля
                            states[obj_type] = [{
                                "id": obj.get("id"),
                                "session_id": obj.get("session_id"),
                                "message": obj.get("message"),
                                "sender": obj.get("sender"),
                                "timestamp": obj.get("timestamp"),
                                "importance": obj.get("importance")
                            } for obj in objects]
                object_states = states

            # Создаем объект снапшота
            snapshot_data = {
                "snapshot_id": snapshot_id,
                "session_id": session_id,
                "object_types": object_types,
                "object_states": object_states,
                "meta": meta,
                "created_at": self._get_rfc3339_timestamp()
            }

            # TODO: Сохранить snapshot_data в память
            return snapshot_data
        except Exception as e:
            print(f"Error creating snapshot: {str(e)}")
            raise

    def _get_object_states(self, object_types):
        """Получает текущее состояние объектов указанных типов"""
        try:
            states = {}
            for obj_type in object_types:
                print(f"\n=== DEBUG: Getting state for {obj_type} ===")
                # Получаем все объекты данного типа
                objects = self._get_all_objects(obj_type)
                print(f"Found {len(objects)} objects of type {obj_type}")

                # Сохраняем их состояние
                states[obj_type] = objects
                print(f"State size for {obj_type}: {len(str(objects))} characters")
                print("==============================\n")
            return states
        except Exception as e:
            print(f"Error getting object states: {str(e)}")
            return {}

    def _get_all_objects(self, object_type):
        """Получает все объекты указанного типа"""
        try:
            print(f"\n=== DEBUG: Getting all objects for {object_type} ===")
            # Получаем коллекцию для данного типа
            collection = self.memory_registry.get(object_type)
            if not collection:
                print(f"Collection {object_type} not found")
                return []

            # Получаем все объекты
            objects = collection.get_all()
            print(f"Found {len(objects)} objects")
            if objects:
                print(f"First object structure: {type(objects[0])}")
                print(f"First object keys: {objects[0].keys() if isinstance(objects[0], dict) else 'Not a dict'}")
            print("==============================\n")
            return objects
        except Exception as e:
            print(f"Error getting objects: {str(e)}")
            return []

    def _get_rfc3339_timestamp(self):
        """Возвращает текущее время в формате RFC3339"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
