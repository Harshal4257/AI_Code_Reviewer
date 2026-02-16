import sys

class customexception(Exception):
    def __init__(self,error_msg,error_details:sys):
        self.error_msg = error_msg
        _,_,exc_tb = error_details.exc_info()
        
        self.file_no = exc_tb.tb_lineno
        self.file_name = exc_tb.tb_frame.f_code.co_filename
        
    def __str__(self):
        return "Error occured in file [{0}] at line [{1}] error message [{2}]".format(self.file_name,self.file_no,str(self.error_msg))
    
if __name__ == "__main__":
    try:
        a = 10 / 0 
    except Exception as e:
        raise customexception(e,sys)