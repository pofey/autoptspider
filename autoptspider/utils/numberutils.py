import cn2an


class NumberUtils:
    @staticmethod
    def crate_number_list(start, end):
        """
        按起点和重点生成一个完整的数字数组，一般用于完整集号的补充
        :param start:
        :param end:
        :return:
        """
        if start is None:
            start = 1
        if end is None:
            return [start]
        if start > end:
            return []
        arr = []
        i = start
        while i <= end:
            arr.append(i)
            i = i + 1
        return arr

    @staticmethod
    def to_number(text):
        """
        文本转化成字符串，支持中文大写数字，如一百二十三
        :param text:
        :return:
        """
        if text is None:
            return None
        if text.isdigit():
            return int(text)
        else:
            try:
                return cn2an.cn2an(text)
            except ValueError as e:
                return None

    @staticmethod
    def trans_unit_to_mb(size: float, unit: str) -> float:
        """
        按文件大小尺寸规格，转换成MB单位的数字
        :param size:
        :param unit:
        :return:
        """
        if unit == 'GB' or unit == 'GiB':
            return round(size * 1024, 2)
        elif unit == 'MB' or unit == 'MiB':
            return round(size, 2)
        elif unit == 'KB' or unit == 'KiB':
            return round(size / 1024, 2)
        elif unit == 'TB' or unit == 'TiB':
            return round(size * 1024 * 1024, 2)
        elif unit == 'PB' or unit == 'PiB':
            return round(size * 1024 * 1024 * 1024, 2)
        else:
            return size

    @staticmethod
    def size_format_from_byte(byte_size: int):
        """
        把一个字节单位的文件尺寸，格式化成一个带单位的字符串
        :param byte_size:
        :return:
        """
        if byte_size is None or byte_size == 0:
            return '0'
        if byte_size < 1048576:
            return f'{round(byte_size / 1024, 2)} KB'
        elif byte_size < 1073741824:
            return f'{round(byte_size / 1024 / 1024, 2)} MB'
        elif byte_size < 1099511627776:
            return f'{round(byte_size / 1024 / 1024 / 1024, 2)} GB'
        elif byte_size < 1125899906842624:
            return f'{round(byte_size / 1024 / 1024 / 1024 / 1024, 2)} TB'

    @staticmethod
    def trans_size_str_to_mb(size: str):
        """
        把一个字符串格式的文件尺寸单位，转换成MB单位的标准数字
        :param size:
        :return:
        """
        if not size:
            return 0.0
        s = None
        u = None
        if size.find(' ') != -1:
            arr = size.split(' ')
            s = arr[0]
            u = arr[1]
        else:
            if size.endswith('GB'):
                s = size[0:-2]
                u = 'GB'
            elif size.endswith('GiB'):
                s = size[0:-3]
                u = 'GB'
            elif size.endswith('MB'):
                s = size[0:-2]
                u = 'MB'
            elif size.endswith('MiB'):
                s = size[0:-3]
                u = 'MB'
            elif size.endswith('KB'):
                s = size[0:-2]
                u = 'KB'
            elif size.endswith('KiB'):
                s = size[0:-3]
                u = 'KB'
            elif size.endswith('TB'):
                s = size[0:-2]
                u = 'TB'
            elif size.endswith('TiB'):
                s = size[0:-3]
                u = 'TB'
            elif size.endswith('PB'):
                s = size[0:-2]
                u = 'PB'
            elif size.endswith('PiB'):
                s = size[0:-3]
                u = 'PB'
        if not s:
            return 0.0
        if s.find(',') != -1:
            s = s.replace(',', '')
        return NumberUtils.trans_unit_to_mb(float(s), u)
