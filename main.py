from pokedex.fetch import get_types, load_type_chart


def main() -> None:
    type_chart = load_type_chart()
    dragonite_types = get_types("dragonite")

    print(f"Loaded {len(type_chart)} types.")
    print(f"Dragonite's types: {dragonite_types}")


if __name__ == "__main__":
    main()