from langchain_community.utilities.requests import RequestsWrapper
import pydantic

print(f"Pydantic version: {pydantic.VERSION}")

try:
    rw = RequestsWrapper()
    print(f"Wrapper type: {type(rw)}")
    print(f"Has get attribute: {hasattr(rw, 'get')}")
    print(f"Dir: {dir(rw)}")
    
    try:
        print(f"Get method: {rw.get}")
    except Exception as e:
        print(f"Error accessing .get: {e}")

except Exception as e:
    print(f"Error initing wrapper: {e}")
