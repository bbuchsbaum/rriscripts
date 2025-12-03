{-# LANGUAGE ScopedTypeVariables #-}
{-# LANGUAGE NamedFieldPuns #-}

module Main (main) where

import Control.Monad (forM, forM_, when)
import Control.Monad.Trans.Class (lift)
import Control.Monad.Trans.Except (ExceptT, runExceptT, throwE)
import Data.Char (isSpace)
import Data.List (intercalate)
import System.Directory
    ( doesDirectoryExist
    , doesFileExist
    , doesPathExist
    , getCurrentDirectory
    , listDirectory
    )
import System.Environment (getArgs)
import System.Exit (exitFailure)
import System.FilePath
    ( (</>)
    , isAbsolute
    , joinPath
    , splitDirectories
    , takeDirectory
    )
import System.IO (hPutStrLn, stderr)

data Mode = Cartesian | Link deriving (Eq, Show)

data OutputMode = Plain | Json deriving (Eq, Show)

data OutputFlags = OutputFlags
    { outMode  :: OutputMode
    , outQuote :: Bool
    } deriving (Show)

data Arg = Arg
    { argName   :: Maybe String
    , argValues :: [String]
    } deriving (Show)

type App = ExceptT String IO

main :: IO ()
main = do
    args <- getArgs
    when (any (`elem` ["-h", "--help"]) args) $ do
        putStrLn usage
        putStrLn examples
        return ()
    result <- runExceptT (run args)
    case result of
        Left err -> hPutStrLn stderr err >> exitFailure
        Right (OutputFlags{outMode}, commands) -> do
            case outMode of
                Plain -> mapM_ putStrLn commands
                Json  -> putStrLn (encodeJsonArray commands)

run :: [String] -> App (OutputFlags, [String])
run rawArgs = do
    let (outFlags, argsNoOutput) = extractOutputFlags rawArgs
    (mode, baseCmd, rawOptions, rawUnnamed) <- parseTopLevel argsNoOutput
    when (null baseCmd) $
        throwE "Error: No base command provided."

    namedArgs <- forM rawOptions $ \(opt, val) -> do
        vals <- expandOptionValues val
        pure Arg { argName = Just opt, argValues = vals }

    unnamedArgs <- forM rawUnnamed $ \val ->
        if isBracketed val
            then Arg Nothing <$> expandOptionValues val
            else pure Arg { argName = Nothing, argValues = [trim val] }

    let allArgs = namedArgs ++ unnamedArgs
    when (any (null . argValues) allArgs) $
        throwE "Error: One of the provided arguments expanded to zero values."

    let tokensPerLine =
            if null allArgs
                then [[]]
                else case mode of
                    Cartesian -> cartesian allArgs
                    Link      -> linked allArgs
        renderFn = if outQuote outFlags then renderCommandQuoted else renderCommand
    pure (outFlags, map (renderFn baseCmd) tokensPerLine)

extractOutputFlags :: [String] -> (OutputFlags, [String])
extractOutputFlags = go (OutputFlags Plain False) []
  where
    go flags acc [] = (flags, reverse acc)
    go flags acc (tok:toks)
        | tok == "--json"  = go flags{outMode = Json} acc toks
        | tok == "--quote" = go flags{outQuote = True} acc toks
        | otherwise        = go flags (tok:acc) toks

parseTopLevel
    :: [String]
    -> App (Mode, String, [(String, String)], [String])
parseTopLevel = go Cartesian "" [] []
  where
    go mode base opts unnamed [] = pure (mode, base, reverse opts, reverse unnamed)
    go mode base opts unnamed (tok:toks)
        | tok == "--link" = go Link base opts unnamed toks
        | "-" `isPrefixOf` tok =
            case toks of
                []      -> throwE $ "Error: No value provided for option '" ++ tok ++ "'."
                (v:vs)
                    | "-" `isPrefixOf` v && not (isBracketed v) ->
                        throwE $ "Error: No value provided for option '" ++ tok ++ "'."
                    | otherwise ->
                        go mode base ((tok, v) : opts) unnamed vs
        | null base =
            go mode tok opts unnamed toks
        | otherwise =
            go mode base opts (tok : unnamed) toks

expandOptionValues :: String -> App [String]
expandOptionValues raw = do
    let trimmed = trim raw
        inner   = dropBrackets trimmed
    expandValueSpec inner

expandValueSpec :: String -> App [String]
expandValueSpec value
    | Just path <- stripPrefix "file:" value = do
        exists <- lift $ doesFileExist path
        if not exists
            then throwE $ "Error: Specified file does not exist: " ++ path
            else do
                contents <- lift $ readFile path
                pure $ filter (not . null) $ map (trim . dropCarriage) (lines contents)
    | Just spec <- stripPrefix "df:" value = do
        case break (== ':') spec of
            (_, "") -> throwE "Error: Malformed df: prefix. Expected df:<column>:<file>."
            (col, rest) ->
                case stripPrefix ":" rest of
                    Nothing     -> throwE "Error: Malformed df: prefix. Expected df:<column>:<file>."
                    Just csvPath -> extractCsvColumn (trim col) (trim csvPath)
    | Just pattern <- stripPrefix "glob:" value = do
        matches <- expandGlob pattern
        if null matches
            then throwE $ "Error: No files match the glob pattern '" ++ pattern ++ "'."
            else pure matches
    | Just (start, end) <- parseRange value =
        pure $ map show $ if start <= end then [start .. end] else [start, (start-1) .. end]
    | otherwise =
        pure $ filter (not . null) $ map (trim . dropCarriage) (splitOnComma value)

cartesian :: [Arg] -> [[String]]
cartesian = foldl step [[]]
  where
    step acc Arg{argName, argValues} =
        [ xs ++ render argName v | xs <- acc, v <- argValues ]

linked :: [Arg] -> [[String]]
linked args =
    let longest = maximum (map (length . argValues) args)
        padded = map (pad longest) args
    in [ concatMap (\(n, vals) -> render n (vals !! i)) padded
       | i <- [0 .. longest - 1]
       ]
  where
    pad n Arg{argName, argValues} =
        let filler = if null argValues then "" else last argValues
            vals   = take n (argValues ++ repeat filler)
        in (argName, vals)

renderCommand :: String -> [String] -> String
renderCommand base tokens = unwords (filter (not . null) (trim base : tokens))

renderCommandQuoted :: String -> [String] -> String
renderCommandQuoted base tokens = unwords (filter (not . null) (shellQuote (trim base) : map shellQuote tokens))

render :: Maybe String -> String -> [String]
render Nothing v  = [trim v]
render (Just n) v = [trim n, trim v]

extractCsvColumn :: String -> FilePath -> App [String]
extractCsvColumn column csvPath = do
    exists <- lift $ doesFileExist csvPath
    if not exists
        then throwE $ "Error: Specified CSV file does not exist: " ++ csvPath
        else do
            contents <- lift $ readFile csvPath
            let ls = lines contents
            when (null ls) $
                throwE $ "Error: CSV file is empty: " ++ csvPath
            let header = map trim (splitOnComma (dropCarriage (head ls)))
                colIndex = lookupIndex column header
            case colIndex of
                Nothing ->
                    throwE $ "Error: Specified column '" ++ column ++ "' does not exist in the CSV file."
                Just idx -> do
                    let rows = tail ls
                    pure [ trim (safeIndex idx (splitOnComma (dropCarriage row)))
                         | row <- rows
                         , not (null (trim row))
                         ]

lookupIndex :: Eq a => a -> [a] -> Maybe Int
lookupIndex target = go 0
  where
    go _ [] = Nothing
    go i (x:xs)
        | x == target = Just i
        | otherwise   = go (i + 1) xs

safeIndex :: Int -> [String] -> String
safeIndex idx xs
    | idx < length xs = xs !! idx
    | otherwise       = ""

expandGlob :: String -> App [FilePath]
expandGlob pattern = do
    let parts = splitDirectories pattern
    (start, rest) <-
        if isAbsolute pattern
            then pure (head parts, tail parts)
            else do
                cwd <- lift getCurrentDirectory
                pure (cwd, parts)
    matches <- go start rest
    pure matches
  where
    go current [] = do
        exists <- lift $ doesPathExist current
        pure [current | exists]
    go current (p:ps)
        | hasWildcards p = do
            isDir <- lift $ doesDirectoryExist current
            if not isDir
                then pure []
                else do
                    entries <- lift $ listDirectory current
                    let hits = filter (matchGlob p) entries
                    fmap concat $
                        forM hits $ \entry ->
                            go (current </> entry) ps
        | otherwise = do
            let next = current </> p
            exists <- lift $ doesPathExist next
            if exists then go next ps else pure []

matchGlob :: String -> String -> Bool
matchGlob "" ""           = True
matchGlob "" _            = False
matchGlob pattern ""      = all (== '*') pattern
matchGlob ('*':ps) str    = any (matchGlob ps . snd) (splits str)
matchGlob ('?':ps) (_:cs) = matchGlob ps cs
matchGlob (p:ps) (c:cs) = p == c && matchGlob ps cs

splits :: [a] -> [([a],[a])]
splits xs = [ splitAt i xs | i <- [0 .. length xs] ]

hasWildcards :: String -> Bool
hasWildcards = any (`elem` ("*?" :: String))

parseRange :: String -> Maybe (Int, Int)
parseRange input =
    let trimmed = trim input
    in case break (`elem` ".:") trimmed of
        (lhs, "") -> Nothing
        (lhs, rest) ->
            let sep = if take 2 rest == ".." then ".." else [head rest]
                rhs = drop (length sep) rest
            in case (readMaybe lhs, readMaybe rhs) of
                (Just a, Just b) -> Just (a, b)
                _                -> Nothing

-- Utilities

readMaybe :: Read a => String -> Maybe a
readMaybe s =
    case reads s of
        [(a,"")] -> Just a
        _        -> Nothing

splitOnComma :: String -> [String]
splitOnComma [] = [""]
splitOnComma s  = split [] s
  where
    split acc [] = [reverse acc]
    split acc (',':xs) = reverse acc : split [] xs
    split acc (x:xs)   = split (x:acc) xs

trim :: String -> String
trim = dropWhile isSpace . dropWhileEnd isSpace

dropWhileEnd :: (a -> Bool) -> [a] -> [a]
dropWhileEnd p = reverse . dropWhile p . reverse

dropCarriage :: String -> String
dropCarriage = reverse . dropWhile (== '\r') . reverse

isPrefixOf :: String -> String -> Bool
isPrefixOf needle hay = take (length needle) hay == needle

stripPrefix :: String -> String -> Maybe String
stripPrefix pre s
    | pre `isPrefixOf` s = Just (drop (length pre) s)
    | otherwise          = Nothing

shellQuote :: String -> String
shellQuote "" = "''"
shellQuote s  = '\'' : concatMap escape s ++ "'"
  where
    escape '\'' = "'\\''"
    escape c    = [c]

encodeJsonArray :: [String] -> String
encodeJsonArray xs = "[" ++ intercalate "," (map encodeJsonString xs) ++ "]"

encodeJsonString :: String -> String
encodeJsonString s = "\"" ++ concatMap esc s ++ "\""
  where
    esc '\\' = "\\\\"
    esc '"'  = "\\\""
    esc '\b' = "\\b"
    esc '\f' = "\\f"
    esc '\n' = "\\n"
    esc '\r' = "\\r"
    esc '\t' = "\\t"
    esc c
        | c < ' ' = "\\u" ++ hex4 (fromEnum c)
        | otherwise = [c]
    hex4 n =
        let hex = "0123456789abcdef"
            d i = hex !! ((n `div` (16 ^ i)) `mod` 16)
        in [d 3, d 2, d 1, d 0]

isBracketed :: String -> Bool
isBracketed s = not (null s) && head s == '[' && last s == ']'

dropBrackets :: String -> String
dropBrackets s
    | isBracketed s = init (tail s)
    | otherwise     = s

usage :: String
usage = unlines
    [ "Usage: cmd-expand [--link] [--quote] [--json] <base_command> [arguments...]"
    , ""
    , "Generates a list of commands by expanding combinations of provided arguments."
    , "Arguments can be named options (e.g., -f [file.txt]) or unnamed values."
    , ""
    , "Modes:"
    , "  Default : Cartesian product of all expanded values."
    , "  --link  : Link arguments by position, repeating the last value of shorter lists."
    , ""
    , "Output controls:"
    , "  --quote : Shell-quote tokens before joining."
    , "  --json  : Emit commands as a JSON array of strings."
    , ""
    , "Value syntax (inside []):"
    , "  val1,val2         Comma-separated list"
    , "  N..M or N:M       Inclusive integer range"
    , "  file:<path>       Lines from file"
    , "  df:<col>:<csv>    CSV column by header name"
    , "  glob:<pattern>    Simple glob (* and ?), relative to CWD unless absolute"
    ]

examples :: String
examples = unlines
    [ "Examples:"
    , "  cmd-expand prog -a [1,2] [x,y]"
    , "  cmd-expand --link task -f [f1,f2] -p [A,B,C]"
    , "  cmd-expand run [1..4] -a [3]"
    ]
