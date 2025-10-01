import grpc
import calculo_pb2
import calculo_pb2_grpc


def run():
    with grpc.insecure_channel("localhost:5000") as channel:
        stub = calculo_pb2_grpc.CalculoServiceStub(channel)

        print("=== Cliente gRPC ===")
        while True:
            print("\nOpciones disponibles:")
            print("1. Sumar (a + b)")
            print("2. Restar (a - b)")
            print("3. Multiplicar (a * b)")
            print("4. Dividir (a / b)")
            print("5. Sumatoria de cuadrados (1..n)")
            print("0. Salir")

            choice = input("Elige una opción: ")

            if choice == "0":
                print("👋 Cerrando cliente...")
                break

            if choice in ["1", "2", "3", "4"]:
                a = int(input("Ingresa a: "))
                b = int(input("Ingresa b: "))
                ops = {"1": "add", "2": "sub", "3": "mul", "4": "div"}
                op = ops[choice]
                request = calculo_pb2.CalculoRequest(op=op, a=a, b=b)

            elif choice == "5":
                n = int(input("Ingresa n: "))
                request = calculo_pb2.CalculoRequest(op="sum_squares", n=n)

            else:
                print("❌ Opción inválida")
                continue

            try:
                response = stub.CalculoTotal(request)
                if response.ok:
                    print(f"✅ Resultado: {response.result}")
                else:
                    print(f"⚠️ Error: {response.error}")
            except Exception as e:
                print(f"❌ Error al comunicarse con el coordinador: {e}")


if __name__ == "__main__":
    run()
