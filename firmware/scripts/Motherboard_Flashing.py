import sys
import glob
import serial
import time
import RPi.GPIO as GPIO


GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
STM32_RST_PIN = 6
GPIO.setup(STM32_RST_PIN,GPIO.OUT) # пин RST для STM32
GPIO.output(STM32_RST_PIN, 1)      # устанавливаем пин RST для STM32 в лог 0
time.sleep(0.2)
GPIO.output(STM32_RST_PIN, 0)      # устанавливаем пин RST для STM32 в лог 0

file = open("../roki-mb-firmware.bin","rb")             #открываем файл прошивки
Sector_Num = 11                                #Кол-во секторов для стирания в STM32 на плате Motherboard
PCB_Name = "PCB_NAME = MOTHERBOARD-V.1.0\r\n"  #Ответ от платы 
Full_Erase = "FULL ERASE OK\r\n"               #Ответ от платы о окончании процесса стирания флэш памяти
Acknowledge = "OK\r\n"                         #Ответ подтверждения об успешности операции

def serial_ports():
    """
    Функция возвращает список, имеющихся COM портов в системе
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result

if __name__ == '__main__':
    
    time.sleep(0.2)
    
    COM_List = serial_ports()
    print("List of available serial ports: ", COM_List)    
    # Проверяем на каком COM порту сидит наша плата
    for COM_Index in range(len(COM_List)):        
        ser = serial.Serial(COM_List[COM_Index], 921600,  timeout = 0.5, write_timeout = 0.5)
        try:
            ser.write("CMD:GET_PCB_NAME\r\n".encode('ascii'))
            response = ser.readline().decode(encoding = 'UTF-8')
        except:
            continue
        if (response == PCB_Name):
            print(response[0:len(response) - 4], "is opened on", COM_List[COM_Index], "device")
            print(" ")
            COM_Motherboard = serial.Serial(COM_List[COM_Index], 921600,  timeout = 2)
            break
        elif (COM_Index >= (len(COM_List) - 1)):
            print("No Motherboard PCB found")
            sys.exit()
    
    time.sleep(0.2)
    
    COM_Motherboard.write("CMD:RESTART\r\n".encode('ascii')) # Делаем сброс STM32
    hello_string = ser.readline().decode(encoding = 'UTF-8') # Получаем сообщение приветствия от платы
    print(hello_string[0:8])                                 # Сообщение успеха перезагрузки STM32
    print(hello_string[8:])                                  # Сообщение идентификатора платы и версии бутлоадера
    
    time.sleep(0.2)
    
    print("Erase in process. Pls wait a few seconds.")
    COM_Motherboard.write("CMD:ERASE\r\n".encode('ascii'))   # Команда для стирания флэш памяти STM32

    for i in range(Sector_Num + 1): 
        sector = COM_Motherboard.readline().decode(encoding = 'UTF-8')            
        if (sector == Full_Erase):
            print("Full erase completed")
            break

    BIN_bytes = list(file.read())
    bin_SIZE = len(BIN_bytes)          #объём прошивки в байтах

    bin_OFFSET = 0
    curr_offset = 0
    value = ""
    offset = ""
    cmd = ""
    current_value = [0xFF, 0xFF, 0xFF, 0xFF]
    bin_OFFSET = 0

    #ser = serial.Serial(COM_List[COM_Index], 921600)
    cmd_list = [None] * 4096
    num_parts = int(bin_SIZE / 1024) #вычисляем кол-во частей по 1 кбайт
    if bin_SIZE % 1024 > 0:
        num_parts += 1
    value = ""
    # начинаем процесс чтения .bin файла и формирования сообщения размером 1кбайт для бутлоадера
    for i in range(num_parts):
        emptyPage = True
        offset = bin_OFFSET
        for q in range(256):  #получаем 256 слов разрядностью 32бит
            for n in range (len(current_value)): #заполняем слово 0xFF
                current_value[n] = 0xFF

            w = len(current_value)
            for k in range(w):                
                index = i + curr_offset + (w - (k + 1)) # не забыть сместить индекс для метаданных если они нужны
                if index >= bin_SIZE:
                    current_value[k] = 0xFF
                else:
                    current_value[k] = BIN_bytes[index]
            
            value = str(value) \
            + str(hex(current_value[0])[2:].zfill(2).upper()) \
            + str(hex(current_value[1])[2:].zfill(2).upper()) \
            + str(hex(current_value[2])[2:].zfill(2).upper()) \
            + str(hex(current_value[3])[2:].zfill(2).upper())
            curr_offset += 4
        bin_OFFSET += 1024
        cmd = "CMD:WRITE:" + str(hex(offset)[2:].zfill(8).upper()) + ":" + str(hex(1024)[2:].zfill(8).upper()) + ">" + value + "\r\n"
        cmd_list[i] = cmd
        value = ""       
        curr_offset = curr_offset - 1    
    
    #print("SIZE = ", str(hex(bin_SIZE)[2:].zfill(8).upper()))
    print("FW_SIZE = ", bin_SIZE, "bytes")
    fw_size = "CMD:SET_SIZE:" + str(hex(bin_SIZE)[2:].zfill(8).upper()) + "\r\n" 
    COM_Motherboard.write(fw_size.encode('ascii')) #отправляем сообщение объёма прошивки в байтах
    
    #print(ser.readline())
    COM_Motherboard.readline()
    print(num_parts, "packages is ready for flashing") #кол-во пакетов по 1кбайт, которые затем будут отправляться бутлоадеру 
    time.sleep(0.2)
    
    for pkg_num in range(num_parts):
        try:
            COM_Motherboard.write(cmd_list[pkg_num].encode('ascii'))
            response = COM_Motherboard.readline().decode(encoding = 'UTF-8')        
            if (response == Acknowledge):
                print("Package", pkg_num + 1, "is flashed")
            else:            
                print("ERROR during flashing")
                COM_Motherboard.write("CMD:RESTART\r\n".encode('ascii'))
                file.close()
                sys.exit()
                break
        except:
            print("Timeout exception")
            sys.exit()
    file.close()
    print(COM_Motherboard.readline().decode(encoding = 'UTF-8')) #получаем последний ответ UPDATE OK! Starting new firmware значит прошивка STM32 прошла успешно


