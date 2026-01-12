try:
    from taxi_service_dev.taxi_engine import TaxiEngine
    print("✅ Import Successful")
except Exception as e:
    print(f"❌ Import Failed: {e}")
except ValueError as e:
    print(f"❌ Value Error (Null Byte): {e}")
