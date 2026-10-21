def stage_one():
    return 1


def stage_two():
    return 2


def target_block():
    return 3


def target(data: bytes):
    if len(data) < 3:
        return None
    if data[0] == 0x41:
        stage_one()
        if data[1] == 0x42:
            stage_two()
            if data[2] == 0x43:
                return target_block()
    return None
