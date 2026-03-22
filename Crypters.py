from calendar import day_abbr


class NoCrypter:
    def __init__(self):
        pass

    def encrypt(self, data):
        return data

    def decrypt(self, data):
        return data

class SymetricCrypter(NoCrypter):
    def __init__(self, key = None):
        #if key == None --> generate it
        self.key = None
        pass

    def get_key(self):
        return self.key

    def encrypt(self, data):
        return data

    def decrypt(self, data):
        return data

class ASymetricCrypter(NoCrypter):
    def __init__(self, key=None):
        # if key == None --> generate it
        self.key = None
        pass

    def get_key(self):
        return self.key

    def encrypt(self, data):
        return data

    def decrypt(self, data):
        return data