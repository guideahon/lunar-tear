Option Explicit

Dim fso, shell, baseDir, pyw, appPy, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = ""

If fso.FileExists("C:\Python312\pythonw.exe") Then
  pyw = "C:\Python312\pythonw.exe"
ElseIf fso.FileExists("C:\Python311\pythonw.exe") Then
  pyw = "C:\Python311\pythonw.exe"
ElseIf fso.FileExists("C:\Python310\pythonw.exe") Then
  pyw = "C:\Python310\pythonw.exe"
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python312\pythonw.exe") Then
  pyw = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python312\pythonw.exe"
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python311\pythonw.exe") Then
  pyw = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python311\pythonw.exe"
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python310\pythonw.exe") Then
  pyw = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python310\pythonw.exe"
Else
  pyw = "pythonw"
End If

appPy = baseDir & "\app.py"
cmd = """" & pyw & """ """ & appPy & """"
shell.Run cmd, 0, False
