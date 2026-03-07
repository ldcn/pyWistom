class CryptographyWnmsClassic:

    ALLOWED_LETTERS = 'U6cefhm1nuLTp8rsxCyzAjatBwEiF5GKklIJgMNOPvQRHSWoVqX2YZ03Dd47b9!"£$%^&_*()<>?#-'
    CRYPT_LETTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-#?<>()*&^%$_£"!'

    def encrypt(self, clear_text: str) -> str:
        seed = 123456 % len(self.CRYPT_LETTERS)
        epassword = "="
        epassword += self.CRYPT_LETTERS[seed]
        epassword += self.CRYPT_LETTERS[(len(clear_text) + seed) %
                                        len(self.CRYPT_LETTERS)]

        for ch in clear_text:
            epassword += self.CRYPT_LETTERS[(
                self.ALLOWED_LETTERS.index(ch) + seed) % len(self.CRYPT_LETTERS)]

        if seed > len(self.CRYPT_LETTERS) // 2:
            epassword += self.CRYPT_LETTERS[seed]

        if seed > len(self.CRYPT_LETTERS) // 3:
            epassword += self.CRYPT_LETTERS[len(clear_text)]

        return epassword

    def decrypt(self, encrypted_text: str) -> str:
        if len(encrypted_text) == 0:
            return encrypted_text

        if encrypted_text[0] == '=':
            seed = self.CRYPT_LETTERS.index(encrypted_text[1])
            length = (self.CRYPT_LETTERS.index(
                encrypted_text[2]) + (len(self.CRYPT_LETTERS) - seed)) % len(self.CRYPT_LETTERS)

            password = ""
            for i in range(length):
                password += self.ALLOWED_LETTERS[
                    (self.CRYPT_LETTERS.index(
                        encrypted_text[i + 3]) + (len(self.CRYPT_LETTERS) - seed)) % len(self.ALLOWED_LETTERS)
                ]
            return password

        return encrypted_text
